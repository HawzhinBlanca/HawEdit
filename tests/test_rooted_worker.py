"""Actual copied worker execution, not model/ASR/production-controller admission."""

from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_linux_prepared_view import DRIVER
from test_linux_scope import PRELUDE, _execute, _source

INIT = (
    PRELUDE
    + r"""
from pathlib import Path
import hashlib,stat
sys.path.insert(0,PACKAGE)
from hawedit.linux_snapshot import LinuxSnapshot,SnapshotMode,SnapshotFile
from hawedit.linux_rooted_worker import RootedCommand,execute_original_worker
from hawedit.linux_thread_registry import LinuxThreadRegistry
assert os.getpid()==1
channel=socket.socket(fileno=int(sys.argv[1]))
prepared=socket.socket(fileno=int(sys.argv[2]))
root=Path(sys.argv[3])
request=channel.recv(64);assert request[:4]==b'HEA1' and len(request)==36
class Header(ctypes.Structure):
 _fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
class Data(ctypes.Structure):
 _fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
assert libc.capset(ctypes.byref(Header(0x20080522,0)),(Data*2)())==0
assert libc.prctl(38,1,0,0,0)==0
ident=b'\x7fELF\x02\x01\x01'+bytes(9)
header=struct.pack('<16sHHIQQQIHHHHHH',ident,2,62,1,0x400078,64,0,0,64,56,1,0,0,0)
segment=struct.pack('<IIQQQQQQ',1,5,0,0x400000,0,132,132,4096)
binary=header+segment+b'\xb8\x3c\x00\x00\x00\xbf\x2a\x00\x00\x00\x0f\x05'
tool=root.parent/'tool';tool.write_bytes(binary)
file=SnapshotFile(tool,'bin/probe',hashlib.sha256(binary).hexdigest(),len(binary),True)
runtime=[]
for name in os.listdir('/proc/self/fd'):
 try:info=os.fstat(int(name))
 except OSError:continue
 if not stat.S_ISREG(info.st_mode):continue
 actual=Path(os.readlink('/proc/self/fd/'+name)).resolve(strict=True)
 data=actual.read_bytes();assert data.startswith(b'\x7fELF')
 runtime.append(SnapshotFile(actual,'runtime/'+name,hashlib.sha256(data).hexdigest(),len(data),True))
files=tuple([*runtime,file])
executable='bin/probe';arguments=();environment=();maximum=8388608
if CASE=='python':
 base=Path('/home/ai/.local/share/uv/python/cpython-3.12.0-linux-x86_64-gnu')
 assert (base/'bin/python3.12').is_file(),'Pinned existing Python runtime unavailable; no fallback'
 selected=[base/'bin/python3.12',base/'lib/libpython3.12.so.1.0']
 selected.extend(path for path in (base/'lib/python3.12').rglob('*') if path.is_file())
 copied=list(files)
 for path in selected:
  actual=path.resolve(strict=True);data=actual.read_bytes()
  copied.append(SnapshotFile(actual,str(path).lstrip('/'),hashlib.sha256(data).hexdigest(),
   len(data),data.startswith(b'\x7fELF')))
 for name in ('libpthread.so.0','libdl.so.2','libutil.so.1','libm.so.6','librt.so.1','libc.so.6'):
  path=Path('/usr/lib/x86_64-linux-gnu')/name;actual=path.resolve(strict=True);data=actual.read_bytes()
  copied.append(SnapshotFile(actual,str(path).lstrip('/'),hashlib.sha256(data).hexdigest(),len(data),True))
 path=Path('/lib64/ld-linux-x86-64.so.2');actual=path.resolve(strict=True);data=actual.read_bytes()
 copied.append(SnapshotFile(actual,str(path).lstrip('/'),hashlib.sha256(data).hexdigest(),len(data),True))
 probe=root.parent/'probe.py'
 probe.write_text("import json,os,sys\n"
  "with open('/proc/self/status') as stream:\n"
  " fields=dict(line.split(':',1) for line in stream if ':' in line)\n"
  "caps=('CapInh','CapPrm','CapEff','CapBnd','CapAmb')\n"
  "assert all(int(fields[k].strip(),16)==0 for k in caps)\n"
  "assert fields['NoNewPrivs'].strip()=='1' and fields['Seccomp'].strip()=='2'\n"
  "assert os.getcwd()=='/' and os.statvfs('/').f_flag&os.ST_RDONLY\n"
  "print(json.dumps({'version':sys.version.split()[0],'nnP':fields['NoNewPrivs'].strip(),'caps_zero':True}))\n",
  encoding='utf-8')
 data=probe.read_bytes();copied.append(SnapshotFile(probe,'probe.py',hashlib.sha256(data).hexdigest(),len(data)))
 files=tuple(copied);executable=str(base/'bin/python3.12').lstrip('/')
 arguments=('-I','-B','/probe.py');environment=(('LD_LIBRARY_PATH',str(base/'lib')),)
 maximum=536870912
command=RootedCommand(files,executable,arguments,environment)
wp,wc=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
wc.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
worker=os.fork()
if worker==0:
 wp.close();channel.close();prepared.close()
 null=os.open('/dev/null',os.O_RDWR|os.O_CLOEXEC)
 for fd in (0,1,2):os.dup2(null,fd)
 os.close(null)
 execute_original_worker(command,wc)
wc.close()
challenge=wp.recv(64);assert challenge[:4]==b'HEW1' and len(challenge)==36,challenge
assert os.WIFSTOPPED(os.waitpid(worker,os.WUNTRACED)[1])
held=[pidfd(1),os.open('/proc/self/ns/pid',os.O_RDONLY|os.O_CLOEXEC),
 os.open('/proc/self/ns/user',os.O_RDONLY|os.O_CLOEXEC),pidfd(worker)]
channel.sendmsg([b'HES1'+request[4:]+struct.pack('!I',4)],
 [(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',held))])
channel.shutdown(socket.SHUT_WR);assert channel.recv(1)==b'G'
original=held[3]
for fd in held[:3]:os.close(fd)
if CASE=='changed':
 # Snapshot accepts the new declared bytes; the immutable forked command must not.
 altered=binary[:-1]+b'\x90';tool.write_bytes(altered)
 files=tuple([*runtime,SnapshotFile(tool,'bin/probe',hashlib.sha256(altered).hexdigest(),len(altered),True)])
snapshot=LinuxSnapshot(root,files,mode=SnapshotMode.ROOTED_IMAGE,
 kernel_entropy=True,max_bytes=maximum)
user=os.open('/proc/self/ns/user',os.O_RDONLY|os.O_CLOEXEC)
mnt=os.open('/proc/self/ns/mnt',os.O_RDONLY|os.O_CLOEXEC)
root_fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
packet=b'HEV1'+challenge[4:]
rights=[user,mnt,root_fd]
if CASE=='nonce':packet=b'HEV1'+b'x'*32
if CASE=='extra':rights.append(os.dup(root_fd))
if CASE=='short':packet=packet[:-1]
if CASE=='wrong_type':rights[0]=os.dup(root_fd)
if CASE=='foreign_root':rights[2]=os.open('/proc',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
if CASE=='foreign_user':
 payload,ancillary,flags,address=channel.recvmsg(1,socket.CMSG_SPACE(4),socket.MSG_CMSG_CLOEXEC)
 assert payload==b'U' and len(ancillary)==1
 original_user=array.array('i');original_user.frombytes(ancillary[0][2])
 assert len(original_user)==1
 rights[0]=original_user[0]
wp.sendmsg([packet],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',rights))])
if CASE=='trailing':wp.send(b'extra')
if CASE=='empty':wp.send(b'')
wp.shutdown(socket.SHUT_WR)
request=prepared.recv(64);assert request[:4]==b'HEQ1' and len(request)==36
prepared.sendmsg([b'HEP1'+request[4:]],
 [(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[user,mnt,root_fd]))])
prepared.shutdown(socket.SHUT_WR)
assert prepared.recv(1)==b'J'
first,ancillary,flags,address=wp.recvmsg(1024,socket.CMSG_SPACE(4),socket.MSG_CMSG_CLOEXEC)
if CASE not in ('none','python'):
 assert first.startswith(b'HEF1'),first
 assert os.waitstatus_to_exitcode(os.waitpid(worker,0)[1])==74
 assert not ancillary
else:
 assert first==b'HEL1'+challenge[4:] and len(ancillary)==1,(first,ancillary)
 listener=array.array('i');listener.frombytes(ancillary[0][2]);assert len(listener)==1
 assert wp.recv(64)==b'HER1'+challenge[4:]
 assert os.WIFSTOPPED(os.waitpid(worker,os.WUNTRACED)[1])
 task=os.open('/proc/2/task',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
 registry=LinuxThreadRegistry(original,task,timeout_seconds=5)
 assert prepared.recv(1)==b'R'
 while not registry.drained:
  registry.poll();time.sleep(.001)
 assert registry.worker_exit==(0 if CASE=='python' else 42) and registry.exec_count==1
 if CASE=='python':
  observed=json.loads(wp.recv(65536))
  assert observed=={'version':'3.12.0','nnP':'1','caps_zero':True},observed
 assert registry.observed_tids==(2,) and registry.reaped_tids==(2,)
 registry.close();os.close(task);os.close(listener[0])
snapshot.verify();snapshot.close()
time.sleep(9)
"""
)


def _worker_run(tmp_path: Path, case: str = "none") -> None:
    package = Path(__file__).parents[1] / "src"
    if os.name == "nt":
        from hawedit.wsl_setup import wsl_path

        located = wsl_path(package, executable="C:/Program Files/WSL/wsl.exe")
    else:
        located = str(package)
    init = INIT.replace("PACKAGE", repr(located)).replace("CASE", repr(case))
    action = (
        f"scope=Scope(left,timeout_seconds={30 if case == 'python' else 5});"
        "view=View(scope,pl);left.send(b'G')\n"
        + (
            "left.sendmsg([b'U'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,"
            "array.array('i',[scope._anchors[2]]))])\n"
            if case == "foreign_user"
            else ""
        )
        + f"view.observe_prepared(timeout_seconds={30 if case == 'python' else 2})\n"
        "view.verify_prepared()\n"
        "original_signal(scope._anchors[3],signal.SIGCONT);pl.send(b'J')\n"
    )
    if case in ("none", "python"):
        action += (
            "end=time.monotonic()+3\n"
            "while True:\n"
            " with open('/proc/'+str(view._ids[1][0])+'/status') as stream:\n"
            "  fields=dict(line.split(':',1) for line in stream if ':' in line)\n"
            " joined=os.readlink('/proc/'+str(view._ids[1][0])+'/ns/mnt')=="
            "os.readlink('/proc/'+str(view._ids[0][0])+'/ns/mnt')\n"
            " if joined and fields['State'].strip().startswith('T ('):break\n"
            " assert time.monotonic()<end;time.sleep(.001)\n"
            "view.verify_joined()\n"
            "assert fields['CapBnd'].strip()=='0000000000000000'\n"
            "assert fields['Seccomp'].strip()=='2'\n"
            "descriptor_root='/proc/'+str(view._ids[1][0])+'/fd/'\n"
            "descriptors=os.listdir(descriptor_root);assert len(descriptors)==5,descriptors\n"
            "kinds=[]\n"
            "for name in descriptors:\n"
            " target=os.readlink(descriptor_root+name)\n"
            " if int(name)<3:assert target=='/dev/null'\n"
            " elif target.startswith('socket:'):kinds.append('channel')\n"
            " else:\n"
            "  with open(descriptor_root+name,'rb') as stream:copied=stream.read(133)\n"
            "  assert copied.startswith(b'\\x7fELF')\n"
            + ("  assert len(copied)==132\n" if case == "none" else "")
            + "  kinds.append('copied_executable')\n"
            "assert sorted(kinds)==['channel','copied_executable']\n"
            "original_signal(scope._anchors[3],signal.SIGCONT);pl.send(b'R')\n"
        )
    action += "assert select.select([scope._anchors[3]],[],[],4)[0]\n"
    driver = DRIVER.replace("SOURCE", repr(_source())).replace("INIT_PROGRAM", repr(init))
    driver = driver.replace("  ACTION", "\n".join("  " + row for row in action.splitlines()))
    result = _execute(tmp_path, driver)
    code = getattr(result, "exit_code", getattr(result, "returncode", None))
    assert code == 0, result.stderr.decode("utf-8", "replace")
    assert json.loads(result.stdout) == {"observed": True}


def test_rooted_worker_actual_copied_elf_is_fenced_and_drained(tmp_path: Path) -> None:
    _worker_run(tmp_path)


def test_rooted_worker_existing_copied_python_starts_without_outside_handles(
    tmp_path: Path,
) -> None:
    _worker_run(tmp_path, "python")


@pytest.mark.parametrize(
    "case",
    ["nonce", "extra", "short", "wrong_type", "foreign_root", "foreign_user", "trailing", "empty"],
)
def test_rooted_worker_prepared_handoff_refuses(tmp_path: Path, case: str) -> None:
    _worker_run(tmp_path, case)


def test_rooted_worker_changed_copied_command_refuses(tmp_path: Path) -> None:
    _worker_run(tmp_path, "changed")


@pytest.mark.parametrize("case", ["path", "unlisted", "nonexec", "argv", "env", "duplicate_env"])
def test_rooted_worker_command_refusals(tmp_path: Path, case: str) -> None:
    snapshot = importlib.import_module("hawedit.linux_snapshot")
    worker = importlib.import_module("hawedit.linux_rooted_worker")
    file = snapshot.SnapshotFile(tmp_path / "tool", "bin/tool", "0" * 64, 132, case != "nonexec")
    options: dict[str, object] = {"files": (file,), "executable": "bin/tool"}
    if case == "path":
        options["executable"] = "../tool"
    if case == "unlisted":
        options["executable"] = "bin/missing"
    if case == "argv":
        options["arguments"] = ["-V"]
    if case == "env":
        options["environment"] = (("BAD=KEY", "value"),)
    if case == "duplicate_env":
        options["environment"] = (("LC_ALL", "C"), ("LC_ALL", "en"))
    with pytest.raises(snapshot.LinuxSnapshotError):
        worker.RootedCommand(**options)


def test_rooted_worker_entry_refuses_host_without_terminating_it() -> None:
    code = (
        "from hawedit.linux_rooted_worker import execute_original_worker\n"
        "from hawedit.linux_snapshot import LinuxSnapshotError\n"
        "try:execute_original_worker(None,None)\n"
        "except LinuxSnapshotError:print('host-refused')\n"
        "else:raise AssertionError('Host accepted worker entry')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, timeout=5, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == b"host-refused"


@pytest.mark.parametrize("case", ["positive", "foreign", "mode", "dirfd", "path"])
@pytest.mark.parametrize("controller_stage", [False, True])
def test_rooted_worker_shared_notification_precedes_write_refusal(
    tmp_path: Path, case: str, controller_stage: bool
) -> None:
    from test_linux_bootstrap import execute
    from thread_name_broker_probe import broker_program

    tree = ast.parse(broker_program(case))
    tree.body[0:0] = ast.parse(
        "from hawedit.linux_snapshot import _install_namespace_fence,_FenceRole\n"
    ).body
    listener = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "original_listener"
    )
    listener.body = ast.parse(
        "count,listener=_install_namespace_fence(native,entropy=True,gpu=False,role=_FenceRole.WORKER)\n"
        "assert listener is not None\nreturn listener"
    ).body
    if controller_stage:

        class ControllerFence(ast.NodeTransformer):
            count = 0

            def visit_Assign(self, node: ast.Assign) -> ast.Assign | list[ast.stmt]:
                if (
                    isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "LinuxThreadRegistry"
                ):
                    self.count += 1
                    statements = ast.parse(
                        "filters,owned_listener=_install_namespace_fence(native,"
                        "entropy=True,gpu=False,role=_FenceRole.CONTROLLER)\n"
                        "assert owned_listener is None"
                    ).body
                    return [*statements, node]
                return node

        visitor = ControllerFence()
        tree = visitor.visit(tree)
        assert visitor.count == 1
    result = execute(tmp_path, ast.unparse(ast.fix_missing_locations(tree)))
    status = getattr(result, "exit_code", getattr(result, "returncode", None))
    assert status == 0, result.stderr.decode("utf-8", "replace")
    row = json.loads(result.stdout)
    assert "error" not in row, row
    assert row["drained"] and row["observed"] == row["reaped"] == [2, 3]
    assert row["readonly_root"] and row["readonly_proc"]
    assert row["broker_result"]["accepted"] == (case == "positive")
    if case == "positive":
        assert row["write_result"] == {"written": 11}
        assert row["measured_comm"] == "Registered"
    else:
        assert row["broker_result"]["descriptor"] is None
        assert row["broker_result"]["error"] == 1
