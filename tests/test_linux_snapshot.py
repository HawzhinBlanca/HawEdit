"""Actual private namespace/copy/fence controls; not model or GPU admission."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from test_linux_bootstrap import execute


def _run(tmp_path: Path, action: str, *, parent: str = "") -> dict[str, Any]:
    package = Path(__file__).parents[1] / "src"
    if os.name == "nt":
        from hawedit.wsl_setup import wsl_path

        located = wsl_path(package, executable="C:/Program Files/WSL/wsl.exe")
    else:
        located = str(package)
    child = (
        "import errno,hashlib,json,os,socket,sys,threading,traceback\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0,{located!r})\n"
        "channel=socket.socket(fileno=int(sys.argv[1]))\n"
        "root=Path(sys.argv[2]);source=Path(sys.argv[3])\n"
        "try:\n"
        " from hawedit.linux_snapshot import LinuxSnapshot,SnapshotFile,LinuxSnapshotError\n"
        " original=source.read_bytes();sha=hashlib.sha256(original).hexdigest()\n"
        + "\n".join(" " + line for line in action.splitlines())
        + "\n channel.send(json.dumps({'observed':True}).encode())\n"
        "except BaseException as exc:\n"
        " record={'error':repr(exc),'traceback':traceback.format_exc()}\n"
        " channel.send(json.dumps(record).encode())\n"
        " sys.exit(1)\n"
    )
    body = (
        "import tempfile\n"
        "base=Path(tempfile.mkdtemp(prefix='hawedit-snapshot-control-'))\n"
        "root=base/'root';root.mkdir(mode=0o700)\n"
        "source=base/'source.bin'\n"
        f"media=Path({located!r}).parent/'tests/fixtures/kurdish-speech-3cuts.mp4'\n"
        "source.write_bytes(media.read_bytes())\n"
        "left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)\n"
        "item=Bootstrap(utility,utility_hash)\n"
        "child=os.fork()\n"
        "if child==0:\n"
        f" command=(sys.executable,'-I','-B','-c',{child!r},"
        "str(right.fileno()),str(root),str(source))\n"
        " item.exec(command,pass_fds=(right.fileno(),))\n"
        "original_pidfd=pidfd(child);right.close()\n"
        "try:\n"
        + "\n".join(" " + line for line in parent.splitlines())
        + "\n assert select.select([left],[],[],8)[0],'Original snapshot child did not return'\n"
        " packet=left.recv(65536);assert packet\n"
        " record=json.loads(packet)\n"
        " assert select.select([original_pidfd],[],[],3)[0],record\n"
        " assert os.waitstatus_to_exitcode(os.waitpid(child,0)[1])==0,record\n"
        " assert not tuple(root.iterdir()),'Private mount leaked into creator'\n"
        " print(json.dumps(record),flush=True)\n"
        "finally:\n"
        " if not select.select([original_pidfd],[],[],0)[0]:\n"
        "  original_signal(original_pidfd)\n"
        "  assert select.select([original_pidfd],[],[],3)[0];os.waitpid(child,0)\n"
        " os.close(original_pidfd);left.close();item.close()\n"
        " assert base.parent==Path('/tmp') and not tuple(root.iterdir())\n"
        " root.rmdir();source.unlink()\n"
        " for path in base.iterdir():path.unlink()\n"
        " base.rmdir()\n"
    )
    result = execute(tmp_path, body)
    status = result.exit_code if os.name == "nt" else result.returncode
    assert status == 0, result.stderr.decode("utf-8", "replace")
    value: dict[str, Any] = json.loads(result.stdout)
    assert value == {"observed": True}
    return value


def test_linux_snapshot_copies_actual_media_and_refuses_mutation(tmp_path: Path) -> None:
    _run(
        tmp_path,
        "file=SnapshotFile(source,'media/source.mp4',sha,len(original))\n"
        "snapshot=LinuxSnapshot(root,(file,),max_bytes=8388608)\n"
        "selected=snapshot.path('media/source.mp4')\n"
        "assert selected.read_bytes()==original\n"
        "assert os.statvfs(root).f_flag & os.ST_RDONLY\n"
        "left_stat,right_stat=selected.stat(),source.stat()\n"
        "assert (left_stat.st_dev,left_stat.st_ino)!=(right_stat.st_dev,right_stat.st_ino)\n"
        "try:selected.write_bytes(b'foreign')\n"
        "except OSError as exc:assert exc.errno==errno.EROFS\n"
        "else:raise AssertionError('Readonly copy accepted mutation')\n"
        "assert selected.read_bytes()==original\n"
        "snapshot.verify();snapshot.close()\n"
        "try:snapshot.path('media/source.mp4')\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Closed snapshot accepted use')",
    )


def test_linux_snapshot_survives_source_backing_mutation(tmp_path: Path) -> None:
    _run(
        tmp_path,
        "snapshot=LinuxSnapshot(root,(SnapshotFile(source,'data.bin',sha,len(original)),),max_bytes=8388608)\n"
        "channel.send(b'copy-ready');assert channel.recv(32)==b'continue'\n"
        "assert source.read_bytes()!=original\n"
        "assert snapshot.path('data.bin').read_bytes()==original\n"
        "snapshot.verify();snapshot.close()",
        parent="assert select.select([left],[],[],8)[0]\n"
        "assert left.recv(32)==b'copy-ready'\n"
        "source.write_bytes(b'changed backing after copy')\n"
        "left.send(b'continue')",
    )


@pytest.mark.parametrize("fault", ["hash", "size", "symlink", "hardlink", "duplicate", "budget"])
def test_linux_snapshot_source_refusals(tmp_path: Path, fault: str) -> None:
    before = "before=source.read_bytes()\n"
    changes = {
        "hash": "declared=SnapshotFile(source,'data.bin','0'*64,len(original))",
        "size": "declared=SnapshotFile(source,'data.bin',sha,len(original)+1)",
        "symlink": "alias=source.parent/'alias';alias.symlink_to(source)\n"
        "declared=SnapshotFile(alias,'data.bin',sha,len(original))",
        "hardlink": "os.link(source,source.parent/'alias')\n"
        "declared=SnapshotFile(source,'data.bin',sha,len(original))",
        "duplicate": "declared=SnapshotFile(source,'data.bin',sha,len(original))",
        "budget": "declared=SnapshotFile(source,'data.bin',sha,len(original))",
    }
    files = "(declared,declared)" if fault == "duplicate" else "(declared,)"
    budget = "1" if fault == "budget" else "8388608"
    _run(
        tmp_path,
        before + changes[fault] + "\ntry:\n"
        f" LinuxSnapshot(root,{files},max_bytes={budget})\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Unsafe source was admitted')\n"
        "assert source.read_bytes()==before",
    )


def test_linux_snapshot_fence_and_inheritance(tmp_path: Path) -> None:
    _run(
        tmp_path,
        "import ctypes,signal\n"
        "snapshot=LinuxSnapshot(root,(SnapshotFile(source,'data.bin',sha,len(original)),),max_bytes=8388608)\n"
        "native=ctypes.CDLL(None,use_errno=True)\n"
        "def refused():\n"
        " ctypes.set_errno(0);assert native.unshare(0x10000000|0x00020000)==-1\n"
        " assert ctypes.get_errno()==errno.EPERM\n"
        "refused()\n"
        "observations=[]\n"
        "def worker():refused();observations.append('refused')\n"
        "thread=threading.Thread(target=worker);thread.start();thread.join(3)\n"
        "assert not thread.is_alive() and observations==['refused']\n"
        "forked=os.fork()\n"
        "if forked==0:\n"
        " refused()\n"
        " try:snapshot.verify()\n"
        " except LinuxSnapshotError:os._exit(0)\n"
        " os._exit(2)\n"
        "assert os.waitstatus_to_exitcode(os.waitpid(forked,0)[1])==0\n"
        "ctypes.set_errno(0);assert native.syscall(0x40000000)==-1\n"
        "assert ctypes.get_errno()==errno.ENOSYS\n"
        "snapshot.verify();snapshot.close()",
    )


def test_linux_snapshot_original_owner_and_descriptor_refusal(tmp_path: Path) -> None:
    _run(
        tmp_path,
        "snapshot=LinuxSnapshot(root,(SnapshotFile(source,'data.bin',sha,len(original)),),max_bytes=8388608)\n"
        "outcomes=[]\n"
        "def foreign():\n"
        " try:snapshot.verify()\n"
        " except LinuxSnapshotError:outcomes.append('refused')\n"
        "thread=threading.Thread(target=foreign);thread.start();thread.join(3)\n"
        "assert not thread.is_alive() and outcomes==['refused']\n"
        "old=snapshot._root_fd;os.close(old)\n"
        "substitute=os.open('/tmp',os.O_RDONLY|os.O_DIRECTORY)\n"
        "try:\n"
        " try:snapshot.verify()\n"
        " except LinuxSnapshotError:pass\n"
        " else:raise AssertionError('Replaced original descriptor accepted')\n"
        " snapshot.close()\n"
        " os.fstat(substitute)\n"
        "finally:os.close(substitute)",
    )


@pytest.mark.parametrize("name", ["", "/absolute", "../escape", "a/../b", "a//b", "./a", "a\x00b"])
def test_linux_snapshot_invalid_declarations(name: str, tmp_path: Path) -> None:
    module = importlib.import_module("hawedit.linux_snapshot")
    with pytest.raises(module.LinuxSnapshotError):
        module.SnapshotFile(tmp_path / "source", name, "0" * 64, 1)


@pytest.mark.parametrize("value", [True, None, "5", 0, -1, float("nan"), float("inf"), 43201])
def test_linux_snapshot_invalid_bounds(value: object, tmp_path: Path) -> None:
    module = importlib.import_module("hawedit.linux_snapshot")
    with pytest.raises(module.LinuxSnapshotError, match="deadline"):
        module.LinuxSnapshot(tmp_path, (), timeout_seconds=value)


def test_linux_snapshot_unsupported_host_or_caller(tmp_path: Path) -> None:
    module = importlib.import_module("hawedit.linux_snapshot")
    with pytest.raises(module.LinuxSnapshotError, match="Linux|dedicated"):
        module.LinuxSnapshot(tmp_path, ())


def test_linux_snapshot_same_inode_foreign_description_cleanup(tmp_path: Path) -> None:
    _run(
        tmp_path,
        "snapshot=LinuxSnapshot(root,(SnapshotFile(source,'data.bin',sha,len(original)),))\n"
        "old=snapshot._root_fd;os.close(old)\n"
        "substitute=os.open('/proc/self/fd/'+str(snapshot._anchor),os.O_RDONLY|os.O_DIRECTORY)\n"
        "if substitute!=old:\n"
        " os.dup2(substitute,old,inheritable=False);os.close(substitute);substitute=old\n"
        "assert substitute==old\n"
        "assert os.fstat(substitute).st_ino==os.fstat(snapshot._anchor).st_ino\n"
        "try:\n"
        " try:snapshot.verify()\n"
        " except LinuxSnapshotError:pass\n"
        " else:raise AssertionError('Same-inode foreign description was admitted')\n"
        " snapshot.close();os.fstat(substitute)\n"
        "finally:os.close(substitute)",
    )


def test_linux_snapshot_root_rename_keeps_original_bytes(tmp_path: Path) -> None:
    _run(
        tmp_path,
        "snapshot=LinuxSnapshot(root,(SnapshotFile(source,'data.bin',sha,len(original)),))\n"
        "selected=snapshot.path('data.bin')\n"
        "channel.send(b'copy-ready');assert channel.recv(32)==b'continue'\n"
        "assert (root/'data.bin').read_bytes()==b'foreign root'\n"
        "assert selected.read_bytes()==original\n"
        "assert snapshot.path('data.bin').read_bytes()==original\n"
        "snapshot.verify();channel.send(b'verified')\n"
        "assert channel.recv(32)==b'finish';snapshot.close()",
        parent="assert select.select([left],[],[],8)[0];assert left.recv(32)==b'copy-ready'\n"
        "moved=base/'renamed';root.rename(moved);root.mkdir(mode=0o700)\n"
        "(root/'data.bin').write_bytes(b'foreign root');left.send(b'continue')\n"
        "assert select.select([left],[],[],8)[0];assert left.recv(32)==b'verified'\n"
        "(root/'data.bin').unlink();root.rmdir();moved.rename(root);left.send(b'finish')",
    )


@pytest.mark.parametrize("fault", ["aggregate", "count", "prefix", "root", "parent", "deadline"])
def test_linux_snapshot_capacity_and_path_refusals(tmp_path: Path, fault: str) -> None:
    changes = {
        "aggregate": "files=(SnapshotFile(source,'a',sha,len(original)),"
        "SnapshotFile(source,'b',sha,len(original)))\noptions={'max_bytes':len(original)}",
        "count": "files=(SnapshotFile(source,'a',sha,len(original)),"
        "SnapshotFile(source,'b',sha,len(original)))\noptions={'max_files':1}",
        "prefix": "files=(SnapshotFile(source,'a/b',sha,len(original)),"
        "SnapshotFile(source,'a',sha,len(original)))\noptions={}",
        "root": "root.chmod(0o755)\nfiles=(SnapshotFile(source,'a',sha,len(original)),)\n"
        "options={}",
        "parent": "alias=source.parent/'alias';alias.symlink_to(source.parent)\n"
        "files=(SnapshotFile(alias/source.name,'a',sha,len(original)),)\noptions={}",
        "deadline": "files=(SnapshotFile(source,'a',sha,len(original)),)\n"
        "options={'timeout_seconds':0.000000001}",
    }
    _run(
        tmp_path,
        "before=source.read_bytes()\n" + changes[fault] + "\ntry:\n"
        " LinuxSnapshot(root,files,**options)\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Unsafe capacity/path/deadline was admitted')\n"
        "assert source.read_bytes()==before",
    )


def test_linux_snapshot_complete_tree_and_kernel_write_refusals(tmp_path: Path) -> None:
    _run(
        tmp_path,
        "import mmap\n"
        "empty=source.parent/'empty';empty.write_bytes(b'')\n"
        "files=(SnapshotFile(source,'media/source.mp4',sha,len(original)),"
        "SnapshotFile(empty,'pkg/__init__.py',hashlib.sha256(b'').hexdigest(),0))\n"
        "snapshot=LinuxSnapshot(root,files,max_bytes=len(original))\n"
        "assert snapshot.path('pkg/__init__.py').read_bytes()==b''\n"
        "selected=snapshot.path('media/source.mp4')\n"
        "for action in (lambda:selected.unlink(),lambda:selected.chmod(0o600),"
        "lambda:selected.rename(selected.parent/'foreign'),"
        "lambda:(selected.parent/'foreign').write_bytes(b'foreign')):\n"
        " try:action()\n"
        " except OSError as exc:assert exc.errno==errno.EROFS\n"
        " else:raise AssertionError('Readonly filesystem mutation succeeded')\n"
        "with selected.open('rb') as stream:\n"
        " try:mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_WRITE)\n"
        " except OSError as exc:assert exc.errno in (errno.EACCES,errno.EPERM)\n"
        " else:raise AssertionError('Read-only description accepted writable mapping')\n"
        "try:snapshot.path('not-declared')\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Undeclared file was exposed')\n"
        "assert selected.read_bytes()==original\n"
        "snapshot.verify();snapshot.close()",
    )


def test_linux_snapshot_namespace_clone_and_exec_fence(tmp_path: Path) -> None:
    _run(
        tmp_path,
        "import ctypes,signal\n"
        "snapshot=LinuxSnapshot(root,(SnapshotFile(source,'data.bin',sha,len(original)),))\n"
        "native=ctypes.CDLL(None,use_errno=True);native.syscall.restype=ctypes.c_long\n"
        "ctypes.set_errno(0)\n"
        "result=native.syscall(ctypes.c_long(56),ctypes.c_ulong(0x10000000|signal.SIGCHLD),"
        "ctypes.c_ulong(0),ctypes.c_ulong(0),ctypes.c_ulong(0),ctypes.c_ulong(0))\n"
        "assert result==-1 and ctypes.get_errno()==errno.EPERM\n"
        "ctypes.set_errno(0);assert native.syscall(ctypes.c_long(435),0,0)==-1\n"
        "assert ctypes.get_errno()==errno.ENOSYS\n"
        "code=('import ctypes,errno; native=ctypes.CDLL(None,use_errno=True); '\n"
        "'assert native.unshare(0x10000000|0x00020000)==-1; '\n"
        "'assert ctypes.get_errno()==errno.EPERM')\n"
        "child=os.fork()\n"
        "if child==0:os.execve(sys.executable,(sys.executable,'-I','-B','-c',code),{})\n"
        "assert os.waitstatus_to_exitcode(os.waitpid(child,0)[1])==0\n"
        "snapshot.verify();snapshot.close()",
    )
