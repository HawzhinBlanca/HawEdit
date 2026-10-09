"""Real original-owner/bootstrap/namespace faults, not model or GPU admission."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from hawedit.studio_private import PrivateDirectory

PRELUDE = r"""
import array,ctypes,errno,fcntl,hashlib,json,os,select,signal,socket,sys,threading,time
from pathlib import Path
signal.alarm(15)
libc=ctypes.CDLL(None,use_errno=True)
opening=libc.pidfd_open;opening.argtypes=[ctypes.c_int,ctypes.c_uint];opening.restype=ctypes.c_int
sending=libc.pidfd_send_signal
sending.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_uint];sending.restype=ctypes.c_int
def pidfd(pid):
 fd=opening(pid,0)
 if fd<0:raise OSError(ctypes.get_errno(),'pidfd_open')
 return fd
def original_signal(fd):
 if sending(fd,signal.SIGKILL,None,0)<0:raise OSError(ctypes.get_errno(),'pidfd_send_signal')
sys.path.insert(0,PACKAGE_ROOT)
from hawedit.linux_bootstrap import LinuxNamespaceBootstrap as Bootstrap
from hawedit.linux_bootstrap import LinuxBootstrapError as Error
from hawedit.linux_scope import LinuxScope
utility=Path('/usr/bin/unshare');utility_hash=hashlib.sha256(utility.read_bytes()).hexdigest()
"""


def execute(tmp_path: Path, body: str) -> Any:
    package = Path(__file__).parents[1] / "src"
    if os.name == "nt":
        from hawedit.native_io import run_native
        from hawedit.wsl_setup import wsl_path

        translated = wsl_path(package, executable="C:/Program Files/WSL/wsl.exe")
        code = PRELUDE.replace("PACKAGE_ROOT", repr(translated)) + "\n" + body
        executable = Path("C:/Program Files/WSL/wsl.exe")
        private = PrivateDirectory(tmp_path / "execution", exclusive=True)
        return run_native(
            (str(executable), "--exec", "/usr/bin/python3", "-I", "-B", "-c", code),
            cwd=private.path,
            environment={
                "SystemRoot": os.environ.get("SYSTEMROOT", "C:/Windows"),
                "USERPROFILE": os.environ["USERPROFILE"],
            },
            expected_executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
            input_bytes=b"",
            timeout_seconds=20,
            output_limit_bytes=262144,
        )
    code = PRELUDE.replace("PACKAGE_ROOT", repr(str(package))) + "\n" + body
    return subprocess.run(
        [sys.executable, "-I", "-B", "-c", code], capture_output=True, timeout=20, check=False
    )


def observe(tmp_path: Path, body: str) -> None:
    result = execute(tmp_path, body + "\nprint(json.dumps({'observed':True}),flush=True)")
    status = result.exit_code if os.name == "nt" else result.returncode
    assert status == 0, result.stderr.decode("utf-8", "replace")
    assert json.loads(result.stdout) == {"observed": True}


def test_linux_bootstrap_unsupported_host(tmp_path: Path) -> None:
    module = importlib.import_module("hawedit.linux_bootstrap")
    if sys.platform == "linux":
        observe(tmp_path, "item=Bootstrap(utility,utility_hash);item.close()")
        return
    with pytest.raises(module.LinuxBootstrapError, match="Linux"):
        module.LinuxNamespaceBootstrap(Path("unshare"), "0" * 64)


@pytest.mark.parametrize("value", [True, None, "5", 0, -1, float("nan"), float("inf"), 43201])
def test_linux_bootstrap_invalid_bounds(value: object) -> None:
    module = importlib.import_module("hawedit.linux_bootstrap")
    with pytest.raises(module.LinuxBootstrapError, match="deadline"):
        module.LinuxNamespaceBootstrap(Path("unshare"), "0" * 64, timeout_seconds=value)


@pytest.mark.parametrize("fault", ["hash", "symlink", "not-elf"])
def test_linux_bootstrap_bad_utility_refuses(tmp_path: Path, fault: str) -> None:
    observe(
        tmp_path,
        "import tempfile\n"
        "with tempfile.TemporaryDirectory() as directory:\n"
        " path=Path(directory)/'unshare';expected=utility_hash\n"
        + (
            " path.write_bytes(utility.read_bytes());expected='0'*64\n"
            if fault == "hash"
            else " path.symlink_to(utility)\n"
            if fault == "symlink"
            else " path.write_bytes(b'not an ELF');"
            "expected=hashlib.sha256(path.read_bytes()).hexdigest()\n"
        )
        + " os.urandom(32);before=len(os.listdir('/proc/self/fd'))\n"
        " try: Bootstrap(path,expected)\n"
        " except Error: pass\n"
        " else: raise AssertionError('Invalid utility admitted')\n"
        " assert len(os.listdir('/proc/self/fd'))==before",
    )


def test_linux_bootstrap_sealed_utility_refuses_mutations(tmp_path: Path) -> None:
    observe(
        tmp_path,
        "item=Bootstrap(utility,utility_hash)\n"
        "assert fcntl.fcntl(item._fd,1034)==63\n"
        "assert hashlib.sha256(os.pread(item._fd,os.fstat(item._fd).st_size,0))"
        ".hexdigest()==utility_hash\n"
        "assert all(not os.get_inheritable(fd) for fd in "
        "(item._fd,item._anchor,item._owner,item._owner_anchor))\n"
        "for operation in (lambda:os.pwrite(item._fd,b'x',0),"
        "lambda:os.ftruncate(item._fd,1),lambda:os.fchmod(item._fd,0)):\n"
        " try:operation()\n"
        " except OSError as exc:assert exc.errno==errno.EPERM\n"
        " else:raise AssertionError('Executable mutation allowed')\n"
        "item.close();item.close()",
    )


def test_linux_bootstrap_parent_cannot_exec(tmp_path: Path) -> None:
    observe(
        tmp_path,
        "item=Bootstrap(utility,utility_hash)\n"
        "try:item.exec((sys.executable,'-I','-B','-c','raise AssertionError(\"unowned exec\")'))\n"
        "except Error as exc:assert 'child' in str(exc)\n"
        "else:raise AssertionError('Parent performed unowned exec')\n"
        "item.close()",
    )


def test_linux_bootstrap_foreign_descriptor(tmp_path: Path) -> None:
    observe(
        tmp_path,
        "item=Bootstrap(utility,utility_hash);foreign=os.open('/dev/null',os.O_RDONLY|os.O_CLOEXEC)\n"
        "os.dup2(foreign,item._fd,inheritable=False)\n"
        "try:item.close()\n"
        "except Error:pass\n"
        "else:raise AssertionError('Foreign FD closed as utility')\n"
        "assert os.fstat(item._fd)==os.fstat(foreign)\n"
        "assert hashlib.sha256(os.pread(item._anchor,os.fstat(item._anchor).st_size,0))"
        ".hexdigest()==utility_hash\n"
        "os.close(foreign)",
    )


INIT = r"""
import array,ctypes,os,select,socket,struct,subprocess,sys,time
assert os.getpid()==1
native=ctypes.CDLL(None,use_errno=True);opening=native.pidfd_open
opening.argtypes=[ctypes.c_int,ctypes.c_uint];opening.restype=ctypes.c_int
channel=socket.socket(fileno=int(sys.argv[1]));request=channel.recv(64)
assert request[:4]==b'HEA1' and len(request)==36
worker=subprocess.Popen([sys.executable,'-I','-B','-c',
 'import os,time;assert os.read(0,1)==b"G";time.sleep(10)'],start_new_session=True,
 stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
held=[opening(os.getpid(),0),os.open('/proc/self/ns/pid',os.O_RDONLY|os.O_CLOEXEC),
 os.open('/proc/self/ns/user',os.O_RDONLY|os.O_CLOEXEC),opening(worker.pid,0)]
assert min(held)>=0
channel.sendmsg([b'HES1'+request[4:]+struct.pack('!I',4)],
 [(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',held))]);channel.shutdown(socket.SHUT_WR)
assert channel.recv(1)==b'G';worker.stdin.write(b'G');worker.stdin.flush()
os.write(int(sys.argv[2]),b'R');time.sleep(10)
"""


@pytest.mark.parametrize("mode", ["normal", "kill"])
def test_linux_bootstrap_original_scope_owner_death(tmp_path: Path, mode: str) -> None:
    observe(
        tmp_path,
        "outer,inside=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)\n"
        "controller=os.fork()\n"
        "if controller==0:\n"
        " outer.close();item=Bootstrap(utility,utility_hash)\n"
        " left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)\n"
        " left.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)\n"
        " ack_read,ack_write=os.pipe2(os.O_CLOEXEC)\n"
        " child=os.fork()\n"
        " if child==0:\n"
        f"  item.exec((sys.executable,'-I','-B','-c',{INIT!r},str(right.fileno()),"
        "str(ack_write)),pass_fds=(right.fileno(),ack_write))\n"
        " original_child=pidfd(child);right.close();os.close(ack_write)\n"
        " scope=LinuxScope(left);scope.require_live();left.send(b'G')\n"
        " assert select.select([ack_read],[],[],2)[0] and os.read(ack_read,1)==b'R'\n"
        " scope.require_live()\n"
        " inside.sendmsg([b'O'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,"
        "array.array('i',[original_child,*scope._held]))])\n"
        " assert inside.recv(1)==b'E'\n"
        " os._exit(0)\n"
        "inside.close();original_controller=pidfd(controller);held=[]\n"
        "try:\n"
        " assert select.select([outer],[],[],5)[0]\n"
        " packet,ancillary,flags,_=outer.recvmsg(1,socket.CMSG_SPACE(20),socket.MSG_CMSG_CLOEXEC)\n"
        " assert packet==b'O' and not flags&~socket.MSG_CMSG_CLOEXEC\n"
        " for level,kind,data in ancillary:\n"
        "  assert (level,kind)==(socket.SOL_SOCKET,socket.SCM_RIGHTS)\n"
        "  values=array.array('i');values.frombytes(data);held.extend(values)\n"
        " assert len(held)==5 and not select.select("
        "[original_controller,held[0],held[1],held[4]],[],[],0)[0]\n"
        + (" outer.send(b'E')\n" if mode == "normal" else " original_signal(original_controller)\n")
        + " for fd in (original_controller,held[0],held[1],held[4]):\n"
        "  assert select.select([fd],[],[],3)[0], 'Original member survived owner death'\n"
        " assert os.waitstatus_to_exitcode(os.waitpid(controller,0)[1])=="
        + ("0\n" if mode == "normal" else "-signal.SIGKILL\n")
        + "finally:\n"
        " for fd in (original_controller,*held[:2],*held[4:]):\n"
        "  if not select.select([fd],[],[],0)[0]:original_signal(fd)\n"
        "  assert select.select([fd],[],[],3)[0]\n"
        " for fd in [original_controller,*held]:os.close(fd)\n"
        " outer.close()",
    )


def test_linux_bootstrap_owner_dead_before_exec_refuses(tmp_path: Path) -> None:
    observe(
        tmp_path,
        "outer,inside=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)\n"
        "controller=os.fork()\n"
        "if controller==0:\n"
        " outer.close();item=Bootstrap(utility,utility_hash);child=os.fork()\n"
        " if child==0:\n"
        "  assert inside.recv(1)==b'G'\n"
        "  try:item.exec((sys.executable,'-I','-B','-c',"
        "'raise AssertionError(\"unowned execution\")'))\n"
        "  except Error:inside.send(b'F');os._exit(71)\n"
        "  os._exit(99)\n"
        " original_child=pidfd(child)\n"
        " inside.sendmsg([b'B'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,"
        "array.array('i',[original_child]))])\n"
        " time.sleep(10);os._exit(0)\n"
        "inside.close();original_controller=pidfd(controller);original_child=None\n"
        "try:\n"
        " assert select.select([outer],[],[],3)[0]\n"
        " packet,ancillary,flags,_=outer.recvmsg(1,socket.CMSG_SPACE(4),socket.MSG_CMSG_CLOEXEC)\n"
        " assert packet==b'B' and not flags&~socket.MSG_CMSG_CLOEXEC\n"
        " assert len(ancillary)==1 and ancillary[0][:2]==(socket.SOL_SOCKET,socket.SCM_RIGHTS)\n"
        " values=array.array('i');values.frombytes(ancillary[0][2]);assert len(values)==1\n"
        " original_child=values[0];assert not select.select([original_child],[],[],0)[0]\n"
        " original_signal(original_controller);"
        "assert select.select([original_controller],[],[],3)[0]\n"
        " assert not select.select([original_child],[],[],0)[0]\n"
        " outer.send(b'G');assert select.select([outer],[],[],3)[0] and outer.recv(1)==b'F'\n"
        " assert select.select([original_child],[],[],3)[0]\n"
        " assert os.waitstatus_to_exitcode(os.waitpid(controller,0)[1])==-signal.SIGKILL\n"
        "finally:\n"
        " for fd in [original_controller,"
        "*([original_child] if original_child is not None else [])]:\n"
        "  if not select.select([fd],[],[],0)[0]:original_signal(fd)\n"
        "  assert select.select([fd],[],[],3)[0];os.close(fd)\n"
        " outer.close()",
    )


@pytest.mark.parametrize("closed_stream", [None, 0, 1, 2])
def test_linux_bootstrap_child_has_isolated_usable_standard_streams(
    tmp_path: Path, closed_stream: int | None
) -> None:
    child = (
        "import os,stat,sys;assert all(os.get_inheritable(fd) and "
        "stat.S_ISCHR(os.fstat(fd).st_mode) and os.fstat(fd).st_rdev==os.makedev(1,3) "
        "for fd in (0,1,2));assert sys.stdin.read()=='';"
        "assert os.write(1,b'not host stdout')==15;assert os.write(2,b'not host stderr')==15;"
        "os.write(int(sys.argv[1]),b'R')"
    )
    observe(
        tmp_path,
        "item=Bootstrap(utility,utility_hash);ack_read,ack_write=os.pipe2(os.O_CLOEXEC)\n"
        "original_streams=[os.fstat(fd) for fd in (0,1,2)]\n"
        "child=os.fork()\n"
        "if child==0:\n"
        + (f" os.close({closed_stream})\n" if closed_stream is not None else "")
        + f" item.exec((sys.executable,'-I','-B','-c',{child!r},"
        "str(ack_write)),pass_fds=(ack_write,))\n"
        "original_child=pidfd(child);os.close(ack_write)\n"
        "try:\n"
        " assert select.select([ack_read],[],[],3)[0] and os.read(ack_read,1)==b'R'\n"
        " assert select.select([original_child],[],[],3)[0]\n"
        " assert os.waitstatus_to_exitcode(os.waitpid(child,0)[1])==0\n"
        " assert [os.fstat(fd) for fd in (0,1,2)]==original_streams\n"
        "finally:\n"
        " if not select.select([original_child],[],[],0)[0]:original_signal(original_child)\n"
        " assert select.select([original_child],[],[],3)[0]\n"
        " os.close(original_child);os.close(ack_read);item.close()",
    )


@pytest.mark.parametrize(
    ("command", "descriptors"),
    [
        ("()", "()"),
        ("[]", "()"),
        ("('/bin/true',None)", "()"),
        ("('relative',)", "()"),
        ("('/bin/true',)", "([],)"),
        ("('/bin/true',)", "(True,)"),
        ("('/bin/true',)", "(0,)"),
        ("('/bin/true',)", "[]"),
    ],
)
def test_linux_bootstrap_invalid_exec_has_contextual_refusal(
    tmp_path: Path, command: str, descriptors: str
) -> None:
    observe(
        tmp_path,
        "item=Bootstrap(utility,utility_hash);child=os.fork()\n"
        "if child==0:\n"
        f" try:item.exec({command},pass_fds={descriptors})\n"
        " except Error:os._exit(0)\n"
        " except Exception:os._exit(81)\n"
        " os._exit(82)\n"
        "original_child=pidfd(child)\n"
        "try:\n"
        " assert select.select([original_child],[],[],3)[0]\n"
        " assert os.waitstatus_to_exitcode(os.waitpid(child,0)[1])==0\n"
        "finally:\n"
        " if not select.select([original_child],[],[],0)[0]:original_signal(original_child)\n"
        " assert select.select([original_child],[],[],3)[0];os.close(original_child);item.close()",
    )


def test_linux_bootstrap_owned_descriptors_close_without_parent_stream_mutation(
    tmp_path: Path,
) -> None:
    observe(
        tmp_path,
        "os.urandom(32);before=len(os.listdir('/proc/self/fd'))\n"
        "streams=[os.fstat(fd) for fd in (0,1,2)]\n"
        "item=Bootstrap(utility,utility_hash)\n"
        "assert len(os.listdir('/proc/self/fd'))==before+4\n"
        "item.close()\n"
        "assert len(os.listdir('/proc/self/fd'))==before\n"
        "assert [os.fstat(fd) for fd in (0,1,2)]==streams",
    )


@pytest.mark.parametrize("closed_stream", [0, 1, 2])
def test_linux_bootstrap_closed_creator_stream_refuses_before_allocation(
    tmp_path: Path, closed_stream: int
) -> None:
    observe(
        tmp_path,
        "os.urandom(32);ack_read,ack_write=os.pipe2(os.O_CLOEXEC)\n"
        "child=os.fork()\n"
        "if child==0:\n"
        f" os.close({closed_stream});before=set(os.listdir('/proc/self/fd'))\n"
        f" streams={{fd:os.fstat(fd) for fd in (0,1,2) if fd!={closed_stream}}}\n"
        " try:Bootstrap(utility,utility_hash)\n"
        " except Error:\n"
        "  assert set(os.listdir('/proc/self/fd'))==before\n"
        "  assert {fd:os.fstat(fd) for fd in streams}==streams\n"
        f"  try:os.fstat({closed_stream})\n"
        "  except OSError as error:assert error.errno==errno.EBADF\n"
        "  else:os._exit(83)\n"
        "  os.write(ack_write,b'F');os._exit(0)\n"
        " os._exit(84)\n"
        "original_child=pidfd(child);os.close(ack_write)\n"
        "try:\n"
        " assert select.select([ack_read],[],[],3)[0] and os.read(ack_read,1)==b'F'\n"
        " assert select.select([original_child],[],[],3)[0]\n"
        " assert os.waitstatus_to_exitcode(os.waitpid(child,0)[1])==0\n"
        "finally:\n"
        " if not select.select([original_child],[],[],0)[0]:original_signal(original_child)\n"
        " assert select.select([original_child],[],[],3)[0]\n"
        " os.close(original_child);os.close(ack_read)",
    )
