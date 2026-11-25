"""Actual copied ELF/root/mutation controls, not model or producer admission."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from test_linux_snapshot import _run


def _rooted_run(tmp_path: Path, action: str, *, parent: str = "") -> None:
    _run(
        tmp_path,
        "import stat\n"
        "runtime_files=[];runtime_descriptions=[]\n"
        "for name in os.listdir('/proc/self/fd'):\n"
        " try:info=os.fstat(int(name))\n"
        " except OSError:continue\n"
        " if not stat.S_ISREG(info.st_mode):continue\n"
        " actual=Path(os.readlink('/proc/self/fd/'+name)).resolve(strict=True)\n"
        " data=actual.read_bytes();assert data[:4]==b'\\x7fELF'\n"
        " runtime_files.append(SnapshotFile(actual,'runtime/'+name,"
        "hashlib.sha256(data).hexdigest(),len(data),executable=True))\n"
        " runtime_descriptions.append((int(name),info.st_dev,info.st_ino))\n" + action,
        parent=parent,
    )


def test_rooted_image_original_root_and_readonly_kernel_state(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "snapshot=LinuxSnapshot(root,(*runtime_files,"
        "SnapshotFile(source,'media/source.mp4',sha,len(original))),"
        "mode=SnapshotMode.ROOTED_IMAGE,max_bytes=8388608)\n"
        "assert os.getcwd()=='/'\n"
        "assert os.stat('/').st_ino==os.fstat(snapshot._anchor).st_ino\n"
        "assert os.stat('/proc/self/root').st_ino==os.fstat(snapshot._anchor).st_ino\n"
        "assert os.statvfs('/').f_flag & os.ST_RDONLY\n"
        "assert os.statvfs('/proc').f_flag & os.ST_RDONLY\n"
        "assert not source.exists()\n"
        "selected=snapshot.path('media/source.mp4').resolve(strict=True)\n"
        "assert selected==Path('/media/source.mp4') and selected.read_bytes()==original\n"
        "for fd,device,inode in runtime_descriptions:\n"
        " assert (os.fstat(fd).st_dev,os.fstat(fd).st_ino)!=(device,inode)\n"
        " assert os.fstat(fd).st_ino==os.stat('/runtime/'+str(fd)).st_ino\n"
        "try:selected.write_bytes(b'foreign')\n"
        "except OSError as exc:assert exc.errno==errno.EROFS\n"
        "else:raise AssertionError('Private root accepted a write')\n"
        "snapshot.verify();snapshot.close()",
    )


def test_rooted_image_normalised_elf_consumer_survives_parent_replacement(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        "import subprocess\n"
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "configuration=source.parent/'config.json';configuration.write_bytes(b'{\"num_beams\":1}\\n')\n"
        "expected=configuration.read_bytes()\n"
        "files=[*runtime_files,SnapshotFile(configuration,'models/config.json',"
        "hashlib.sha256(expected).hexdigest(),len(expected))]\n"
        "for path,name in (('/usr/bin/dash','bin/dash'),"
        "('/usr/lib/x86_64-linux-gnu/libc.so.6','usr/lib/x86_64-linux-gnu/libc.so.6'),"
        "('/lib64/ld-linux-x86-64.so.2','lib64/ld-linux-x86-64.so.2')):\n"
        " actual=Path(path).resolve(strict=True);data=actual.read_bytes()\n"
        " assert data[:4]==b'\\x7fELF'\n"
        " files.append(SnapshotFile(actual,name,hashlib.sha256(data).hexdigest(),"
        "len(data),executable=True))\n"
        "snapshot=LinuxSnapshot(root,tuple(files),mode=SnapshotMode.ROOTED_IMAGE,max_bytes=8388608)\n"
        "channel.send(b'copy-ready');assert channel.recv(32)==b'continue'\n"
        "selected=snapshot.path('models/config.json').resolve(strict=True)\n"
        "assert selected==Path('/models/config.json')\n"
        "result=subprocess.run(['/bin/dash','-c',"
        '\'IFS= read -r line < "$1"; printf "%s\\n" "$line"\',\'--\',str(selected)],'
        "capture_output=True,timeout=3,check=False,env={'PATH':'/bin','LC_ALL':'C'})\n"
        "assert result.returncode==0,result.stderr\n"
        "assert result.stdout==expected\n"
        "assert not configuration.exists() and not source.exists()\n"
        "assert os.stat('/bin/dash').st_mode & 0o777==0o500\n"
        "snapshot.verify();channel.send(b'verified')\n"
        "assert channel.recv(32)==b'finish';snapshot.close()",
        parent="assert select.select([left],[],[],8)[0]\n"
        "packet=left.recv(65536);assert packet==b'copy-ready',packet\n"
        "moved=base/'renamed';root.rename(moved);root.mkdir(mode=0o700)\n"
        "(root/'models').mkdir();(root/'models/config.json').write_bytes(b'foreign')\n"
        "left.send(b'continue')\n"
        "assert select.select([left],[],[],8)[0];assert left.recv(32)==b'verified'\n"
        "(root/'models/config.json').unlink();(root/'models').rmdir();root.rmdir()\n"
        "moved.rename(root);left.send(b'finish')",
    )


@pytest.mark.parametrize("name", ["proc", "proc/self/status", "proc/data/file"])
def test_rooted_image_reserved_proc_refuses(tmp_path: Path, name: str) -> None:
    _run(
        tmp_path,
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "try:\n"
        f" LinuxSnapshot(root,(SnapshotFile(source,{name!r},sha,len(original)),),"
        "mode=SnapshotMode.ROOTED_IMAGE)\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Declared bytes replaced kernel proc')\n"
        "assert source.read_bytes()==original and not tuple(root.iterdir())",
    )


@pytest.mark.parametrize("value", [True, "rooted_image", None, 1])
def test_rooted_image_typed_mode_refuses(tmp_path: Path, value: object) -> None:
    _run(
        tmp_path,
        "try:\n"
        " LinuxSnapshot(root,(SnapshotFile(source,'data',sha,len(original)),),"
        f"mode={value!r})\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Untyped rooted mode admitted')",
    )


@pytest.mark.parametrize("value", [1, 0, "yes", None])
def test_rooted_image_executable_declaration_refusals(tmp_path: Path, value: object) -> None:
    module = importlib.import_module("hawedit.linux_snapshot")
    with pytest.raises(module.LinuxSnapshotError):
        module.SnapshotFile(tmp_path / "input", "bin/tool", "0" * 64, 1, executable=value)


def test_rooted_image_capacity_and_default_bounds(tmp_path: Path) -> None:
    module = importlib.import_module("hawedit.linux_snapshot")
    plain = module.SnapshotFile(tmp_path / "source", "data", "0" * 64, 1)
    executable = module.SnapshotFile(tmp_path / "source", "bin/tool", "0" * 64, 1, executable=True)
    assert module.LinuxSnapshot._declarations(
        tmp_path, (plain,), 128 * 1024**3, 4096, module.SnapshotMode.ROOTED_IMAGE
    ) == {"data"}
    for files, maximum, count, mode in (
        ((plain,), 128 * 1024**3 + 1, 4096, module.SnapshotMode.ROOTED_IMAGE),
        ((plain,), 32 * 1024**3 + 1, 4096, module.SnapshotMode.DATA_ONLY),
        ((executable,), 1024**3, 4096, module.SnapshotMode.DATA_ONLY),
        ((plain,), 1024**3, 0, module.SnapshotMode.ROOTED_IMAGE),
    ):
        with pytest.raises(module.LinuxSnapshotError):
            module.LinuxSnapshot._declarations(tmp_path, files, maximum, count, mode)


@pytest.mark.parametrize("kind", ["directory", "regular"])
def test_rooted_image_outside_descriptions_refuse(tmp_path: Path, kind: str) -> None:
    opened = (
        "os.open(source.parent,os.O_RDONLY|os.O_DIRECTORY)"
        if kind == "directory"
        else ("os.open(source,os.O_RDONLY)")
    )
    _rooted_run(
        tmp_path,
        "from hawedit.linux_snapshot import SnapshotMode\n"
        f"outside={opened}\n"
        "try:\n"
        " try:\n"
        "  LinuxSnapshot(root,(*runtime_files,SnapshotFile(source,'data',sha,len(original))),"
        "mode=SnapshotMode.ROOTED_IMAGE)\n"
        " except LinuxSnapshotError:pass\n"
        " else:raise AssertionError('Outside file/directory description admitted')\n"
        " os.fstat(outside)\n"
        " assert source.read_bytes()==original\n"
        "finally:os.close(outside)",
    )


def test_rooted_image_original_root_substitution_refuses(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "snapshot=LinuxSnapshot(root,(*runtime_files,SnapshotFile(source,'data',sha,len(original))),"
        "mode=SnapshotMode.ROOTED_IMAGE)\n"
        "os.chdir('/proc')\n"
        "try:snapshot.verify()\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Changed original current-directory admitted')\n"
        "snapshot.close()",
    )


def test_rooted_image_reentry_thread_and_fork_refuse(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        "import ctypes\n"
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "snapshot=LinuxSnapshot(root,(*runtime_files,SnapshotFile(source,'data',sha,len(original))),"
        "mode=SnapshotMode.ROOTED_IMAGE)\n"
        "native=ctypes.CDLL(None,use_errno=True)\n"
        "ctypes.set_errno(0);assert native.unshare(0x10000000|0x00020000)==-1\n"
        "assert ctypes.get_errno()==errno.EPERM\n"
        "outcomes=[]\n"
        "def foreign():\n"
        " try:snapshot.verify()\n"
        " except LinuxSnapshotError:outcomes.append('refused')\n"
        "thread=threading.Thread(target=foreign);thread.start();thread.join(3)\n"
        "assert not thread.is_alive() and outcomes==['refused']\n"
        "child=os.fork()\n"
        "if child==0:\n"
        " try:snapshot.verify()\n"
        " except LinuxSnapshotError:os._exit(0)\n"
        " os._exit(2)\n"
        "assert os.waitstatus_to_exitcode(os.waitpid(child,0)[1])==0\n"
        "snapshot.verify();snapshot.close()",
    )


def test_rooted_image_retained_runtime_description_and_callbacks(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        "import ctypes\n"
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "assert runtime_descriptions,'Actual libffi retained description required'\n"
        "positions={fd:os.lseek(fd,7,os.SEEK_SET) for fd,_,_ in runtime_descriptions}\n"
        "snapshot=LinuxSnapshot(root,(*runtime_files,SnapshotFile(source,'data',sha,len(original))),"
        "mode=SnapshotMode.ROOTED_IMAGE)\n"
        "for fd,device,inode in runtime_descriptions:\n"
        " assert os.lseek(fd,0,os.SEEK_CUR)==positions[fd]\n"
        " assert (os.fstat(fd).st_dev,os.fstat(fd).st_ino)!=(device,inode)\n"
        " assert os.fstat(fd).st_ino==os.stat('/runtime/'+str(fd)).st_ino\n"
        "callback=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_int)\n"
        "callbacks=[callback(lambda value:value+1) for _ in range(5000)]\n"
        "assert all(item(8)==9 for item in callbacks)\n"
        "snapshot.verify();snapshot.close()\n"
        "assert callbacks[-1](9)==10\n"
        "for fd,_,_ in runtime_descriptions:os.fstat(fd)",
    )


def test_rooted_image_retained_same_inode_new_description_refuses(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "assert runtime_descriptions\n"
        "snapshot=LinuxSnapshot(root,(*runtime_files,SnapshotFile(source,'data',sha,len(original))),"
        "mode=SnapshotMode.ROOTED_IMAGE)\n"
        "fd=runtime_descriptions[0][0]\n"
        "other=os.open('/runtime/'+str(fd),os.O_RDONLY)\n"
        "try:\n"
        " os.dup2(other,fd,inheritable=False)\n"
        " try:snapshot.verify()\n"
        " except LinuxSnapshotError:pass\n"
        " else:raise AssertionError('Reopened retained description admitted')\n"
        " snapshot.close();os.fstat(fd)\n"
        "finally:os.close(other)",
    )


@pytest.mark.parametrize("fault", ["writable", "inheritable", "nonexecutable", "wrong_hash"])
def test_rooted_image_retained_runtime_refusals(tmp_path: Path, fault: str) -> None:
    change = {
        "writable": "outside=os.open(source,os.O_RDWR)\n",
        "inheritable": "outside=os.open(source,os.O_RDONLY);os.set_inheritable(outside,True)\n",
        "nonexecutable": "outside=os.open(source,os.O_RDONLY)\n",
        "wrong_hash": "outside=os.open(source,os.O_RDONLY)\n",
    }[fault]
    digest = "'0'*64" if fault == "wrong_hash" else "sha"
    executable = "False" if fault == "nonexecutable" else "True"
    _rooted_run(
        tmp_path,
        "from hawedit.linux_snapshot import SnapshotMode\n"
        + change
        + "try:\n"
        + f" item=SnapshotFile(source,'bin/input',{digest},len(original),executable={executable})\n"
        + " try:LinuxSnapshot(root,(*runtime_files,item),mode=SnapshotMode.ROOTED_IMAGE)\n"
        + " except LinuxSnapshotError:pass\n"
        + " else:raise AssertionError('Unsafe retained outside description admitted')\n"
        + " os.fstat(outside);assert source.read_bytes()==original\n"
        + "finally:os.close(outside)",
    )


def test_rooted_image_kernel_initializer_loss_is_irreversible(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        "import ctypes\n"
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "class Rule(ctypes.Structure):\n"
        " _fields_=[('code',ctypes.c_ushort),('jt',ctypes.c_ubyte),"
        "('jf',ctypes.c_ubyte),('k',ctypes.c_uint32)]\n"
        "class Program(ctypes.Structure):\n"
        " _fields_=[('len',ctypes.c_ushort),('filter',ctypes.POINTER(Rule))]\n"
        "rules=(Rule*4)(Rule(0x20,0,0,0),Rule(0x15,0,1,272),"
        "Rule(0x06,0,0,0x50000|errno.EPERM),Rule(0x06,0,0,0x7fff0000))\n"
        "program=Program(4,rules);native=ctypes.CDLL(None,use_errno=True)\n"
        "native.prctl.argtypes=[ctypes.c_int,*([ctypes.c_ulong]*4)]\n"
        "assert native.prctl(22,2,ctypes.addressof(program),0,0)==0\n"
        "try:LinuxSnapshot(root,(*runtime_files,SnapshotFile(source,'data',sha,len(original))),"
        "mode=SnapshotMode.ROOTED_IMAGE)\n"
        "except LinuxSnapshotError as exc:\n"
        " assert isinstance(exc.__cause__,OSError) and exc.__cause__.errno==errno.EPERM\n"
        "else:raise AssertionError('Denied kernel initializer admitted')\n"
        "try:LinuxSnapshot(root,(*runtime_files,SnapshotFile(source,'data',sha,len(original))),"
        "mode=SnapshotMode.ROOTED_IMAGE)\n"
        "except LinuxSnapshotError as exc:assert 'fresh dedicated' in str(exc)\n"
        "else:raise AssertionError('Failed irreversible initializer retried')\n"
        "assert not tuple(root.iterdir()) and source.read_bytes()==original",
    )


def test_rooted_image_same_inode_reopened_root_is_not_original(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "snapshot=LinuxSnapshot(root,(*runtime_files,SnapshotFile(source,'data',sha,len(original))),"
        "mode=SnapshotMode.ROOTED_IMAGE)\n"
        "replacement=os.open('/',os.O_RDONLY|os.O_DIRECTORY)\n"
        "try:\n"
        " os.dup2(replacement,snapshot._root_fd,inheritable=False)\n"
        " assert os.fstat(snapshot._root_fd).st_ino==os.fstat(snapshot._anchor).st_ino\n"
        " try:snapshot.verify()\n"
        " except LinuxSnapshotError:pass\n"
        " else:raise AssertionError('Reopened root description admitted')\n"
        " foreign=snapshot._root_fd;snapshot.close();os.fstat(foreign)\n"
        " assert Path('/data').read_bytes()==original\n"
        "finally:os.close(replacement)",
    )
