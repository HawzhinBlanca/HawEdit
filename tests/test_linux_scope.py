"""Actual original Linux namespace/member capabilities, not GPU/effect admission."""

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

PRELUDE = r"""
import array,ctypes,errno,fcntl,json,os,select,signal,socket,struct,subprocess,sys,threading,time
signal.alarm(12)
libc=ctypes.CDLL(None,use_errno=True)
opening=libc.pidfd_open; opening.argtypes=[ctypes.c_int,ctypes.c_uint]; opening.restype=ctypes.c_int
sending=libc.pidfd_send_signal
sending.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_uint]
sending.restype=ctypes.c_int
def pidfd(pid):
 fd=opening(pid,0)
 if fd<0: raise OSError(ctypes.get_errno(),'pidfd_open')
 return fd
def original_signal(fd,number):
 if sending(fd,number,None,0)<0: raise OSError(ctypes.get_errno(),'pidfd_send_signal')
"""

INIT = (
    PRELUDE
    + r"""
assert os.getpid()==1
channel=socket.socket(fileno=int(sys.argv[1]))
assert select.select([channel],[],[],4)[0]
request=channel.recv(64); assert len(request)==36 and request[:4]==b'HEA1'
nonce=request[4:]
worker=subprocess.Popen([sys.executable,'-I','-B','-c',
 'import os,signal,time; signal.alarm(10); assert os.read(0,1)==b\"G\"; time.sleep(9)'],
 start_new_session=True,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
assert worker.stdin is not None
held=[pidfd(os.getpid()),os.open('/proc/self/ns/pid',os.O_RDONLY|os.O_CLOEXEC),
 os.open('/proc/self/ns/user',os.O_RDONLY|os.O_CLOEXEC),pidfd(worker.pid)]
packet=b'HES1'+nonce+struct.pack('!I',len(held))
FAULT
channel.sendmsg([packet],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',held))])
if globals().get('duplicate_packet',False):
 channel.sendmsg([packet],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',held))])
if not globals().get('no_eof',False): channel.shutdown(socket.SHUT_WR)
assert select.select([channel],[],[],6)[0]
release=channel.recv(1)
if release==b'G':
 worker.stdin.write(b'G');worker.stdin.flush();os.write(int(sys.argv[2]),b'R')
time.sleep(9)
"""
)

DRIVER = (
    PRELUDE
    + r"""
ns={'__name__':'hawedit_linux_scope_under_test'}
exec(compile(SOURCE,'linux_scope.py','exec'),ns)
Scope=ns['LinuxScope'];Error=ns['LinuxScopeError']
left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
left.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
ack_read,ack_write=os.pipe2(os.O_CLOEXEC)
init=INIT_PROGRAM
manager=subprocess.Popen(['/usr/bin/unshare','--user','--map-current-user','--pid','--fork',
 '--kill-child=SIGKILL','--mount-proc',sys.executable,'-I','-B','-c',init,str(right.fileno()),str(ack_write)],
 pass_fds=(right.fileno(),ack_write),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
original_manager=pidfd(manager.pid)
right.close()
os.close(ack_write)
scope=None
try:
 ACTION
 print(json.dumps({'observed':True}),flush=True)
finally:
 if not select.select([original_manager],[],[],0)[0]:
  original_signal(original_manager,signal.SIGKILL)
 assert select.select([original_manager],[],[],4)[0]
 manager.wait(timeout=1)
 assert manager.stderr is not None
 manager.stderr.close()
 os.close(original_manager);left.close();os.close(ack_read)
"""
)


def _source() -> str:
    path = Path(__file__).parents[1] / "src/hawedit/linux_scope.py"
    assert path.is_file(), "Original Linux scope API not implemented"
    return path.read_text(encoding="utf-8")


def _execute(tmp_path: Path, code: str) -> Any:
    if os.name == "nt":
        from hawedit.native_io import run_native
        from hawedit.studio_private import PrivateDirectory

        executable = Path("C:/Program Files/WSL/wsl.exe")
        private = PrivateDirectory(tmp_path / "execution", exclusive=True)
        return run_native(
            (str(executable), "--exec", "/usr/bin/python3", "-I", "-B", "-"),
            cwd=private.path,
            environment={
                "SystemRoot": os.environ.get("SYSTEMROOT", "C:/Windows"),
                "USERPROFILE": os.environ["USERPROFILE"],
            },
            expected_executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
            input_bytes=code.encode("utf-8"),
            timeout_seconds=20,
            output_limit_bytes=262144,
        )
    return subprocess.run(
        [sys.executable, "-I", "-B", "-"],
        input=code.encode("utf-8"),
        capture_output=True,
        timeout=20,
        check=False,
    )


def _drive(tmp_path: Path, action: str, *, fault: str = "pass") -> None:
    code = (
        DRIVER.replace("SOURCE", repr(_source()))
        .replace("INIT_PROGRAM", repr(INIT.replace("FAULT", fault)))
        .replace(" ACTION", "\n".join(" " + line for line in action.splitlines()))
    )
    result = _execute(tmp_path, code)
    status = result.exit_code if os.name == "nt" else result.returncode
    assert status == 0, result.stderr.decode("utf-8", "replace")
    assert json.loads(result.stdout) == {"observed": True}


def test_linux_scope_unsupported_host_refuses(tmp_path: Path) -> None:
    module = importlib.import_module("hawedit.linux_scope")
    if sys.platform == "linux":
        _drive(tmp_path, "scope=Scope(left);scope.stop(timeout_seconds=2);scope.close()")
        return
    with pytest.raises(module.LinuxScopeError, match="Linux"):
        module.LinuxScope(None)


@pytest.mark.parametrize(
    "value", [True, False, None, "5", 0, -1, float("nan"), float("inf"), 43201]
)
def test_linux_scope_invalid_bounds_refuse(value: object) -> None:
    module = importlib.import_module("hawedit.linux_scope")
    with pytest.raises(module.LinuxScopeError, match="deadline"):
        module.LinuxScope(None, timeout_seconds=value)


def test_linux_scope_retains_original_descriptors(tmp_path: Path) -> None:
    _drive(
        tmp_path,
        "scope=Scope(left);scope.require_live()\n"
        "assert all(not os.get_inheritable(fd) for fd in scope._held)\n"
        "assert len(scope._held)==4 and len(scope._anchors)==4\n"
        "assert left.getblocking()\n"
        "scope.stop(timeout_seconds=2);scope.close();scope.close()",
    )


def test_linux_scope_stop_observes_original_detached_member(tmp_path: Path) -> None:
    _drive(
        tmp_path,
        "scope=Scope(left);scope.require_live()\n"
        "left.send(b'G')\n"
        "assert select.select([ack_read],[],[],2)[0] and os.read(ack_read,1)==b'R'\n"
        "scope.require_live();scope.stop(timeout_seconds=2)\n"
        "assert all(select.select([fd],[],[],0)[0] for fd in (scope._held[0],*scope._held[3:]))\n"
        "scope.close()",
    )


@pytest.mark.parametrize(
    "fault",
    [
        "packet=b'BAD!'+packet[4:]",
        "packet=b'HES1'+b'x'*32+packet[36:]",
        "packet=packet[:-1]",
        "packet=packet[:-4]+struct.pack('!I',5)",
        "held[-1]=held[0]",
        "held[1],held[2]=held[2],held[1]",
        "held[-1]=os.open('/dev/null',os.O_RDONLY|os.O_CLOEXEC)",
        "held[-1]=os.open('/proc/self/ns/pid',os.O_RDONLY|os.O_CLOEXEC)",
        "held=held[:-1]",
        "held=held+[held[-1]]*128;packet=packet[:-4]+struct.pack('!I',len(held))",
        "duplicate_packet=True",
        "no_eof=True",
    ],
)
def test_linux_scope_invalid_handoff_refuses(tmp_path: Path, fault: str) -> None:
    _drive(
        tmp_path,
        "try: Scope(left,timeout_seconds=.5)\n"
        "except Error: pass\n"
        "else: raise AssertionError('Invalid original handoff admitted')\n"
        "try: Scope(left,timeout_seconds=.5)\n"
        "except Error as exc: assert 'retained' in str(exc)\n"
        "else: raise AssertionError('Uncertain handoff admitted again')",
        fault=fault,
    )


def test_linux_scope_substitution_retains_uncertainty(tmp_path: Path) -> None:
    _drive(
        tmp_path,
        "scope=Scope(left)\n"
        "foreign=os.open('/dev/null',os.O_RDONLY|os.O_CLOEXEC)\n"
        "os.dup2(foreign,scope._held[0],inheritable=False)\n"
        "try: scope.require_live()\n"
        "except Error: pass\n"
        "else: raise AssertionError('Substitution accepted')\n"
        "try: scope.close()\n"
        "except Error: pass\n"
        "else: raise AssertionError('Uncertainty released')\n"
        "assert os.fstat(scope._held[0])==os.fstat(foreign)\n"
        "assert not select.select([scope._anchors[0]],[],[],0)[0]\n"
        "os.close(foreign)",
    )


def test_linux_scope_foreign_creator_refuses(tmp_path: Path) -> None:
    _drive(
        tmp_path,
        "scope=Scope(left);refused=[]\n"
        "def other():\n"
        " try: scope.require_live()\n"
        " except Error as exc: refused.append(str(exc))\n"
        "thread=threading.Thread(target=other);thread.start();thread.join(1)\n"
        "assert not thread.is_alive() and len(refused)==1 and 'creator' in refused[0]\n"
        "scope.require_live();scope.stop(timeout_seconds=2);scope.close()",
    )


def test_linux_scope_uncertainty_refuses_reentry(tmp_path: Path) -> None:
    _drive(
        tmp_path,
        "scope=Scope(left)\n"
        "try: Scope(left)\n"
        "except Error as exc: assert 'retained' in str(exc)\n"
        "else: raise AssertionError('Concurrent original scope admitted')\n"
        "scope.stop(timeout_seconds=2);scope.close()",
    )


def test_linux_scope_empty_packet_does_not_seal_handoff(tmp_path: Path) -> None:
    _drive(
        tmp_path,
        "try: Scope(left,timeout_seconds=.5)\n"
        "except Error: pass\n"
        "else: raise AssertionError('Empty packet claimed original write shutdown')",
        fault="channel.sendmsg([packet],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',held))]);"
        "channel.send(b'');no_eof=True",
    )


def test_linux_scope_invalid_handoff_closes_all_received_rights(tmp_path: Path) -> None:
    _drive(
        tmp_path,
        "try: Scope(left,timeout_seconds=.5)\n"
        "except Error: pass\n"
        "else: raise AssertionError('Wrong handoff admitted')\n"
        "retained=ns['_ACTIVE'];assert retained is not None and retained._failed\n"
        "assert len(retained._held)==4 and all(fd==-1 for fd in retained._held)\n"
        "assert retained._socket.fileno()==-1\n"
        "assert not select.select([original_manager],[],[],0)[0]",
        fault="packet=b'BAD!'+packet[4:]",
    )


def test_linux_scope_clean_close_releases_owned_not_borrowed_descriptors(tmp_path: Path) -> None:
    _drive(
        tmp_path,
        # Python 3.12 may retain its first-use entropy FD; it is not scope-owned.
        "os.urandom(32)\n"
        "before=len(os.listdir('/proc/self/fd'))\n"
        "scope=Scope(left);scope.stop(timeout_seconds=2);scope.close()\n"
        "assert len(os.listdir('/proc/self/fd'))==before\n"
        "assert left.fileno()>=0 and os.fstat(left.fileno())\n"
        "assert ns['_ACTIVE'] is None",
    )


def test_linux_scope_forked_creator_cannot_signal_original_scope(tmp_path: Path) -> None:
    _drive(
        tmp_path,
        "scope=Scope(left);child=os.fork()\n"
        "if child==0:\n"
        " try: scope.stop(timeout_seconds=1)\n"
        " except Error as exc: os._exit(0 if 'creator' in str(exc) else 82)\n"
        " os._exit(83)\n"
        "original_child=pidfd(child)\n"
        "assert select.select([original_child],[],[],2)[0]\n"
        "assert os.waitstatus_to_exitcode(os.waitpid(child,0)[1])==0\n"
        "os.close(original_child);scope.require_live()\n"
        "scope.stop(timeout_seconds=2);scope.close()",
    )


@pytest.mark.parametrize("value", [True, 0, -1, float("nan"), float("inf"), 43201])
def test_linux_scope_invalid_stop_deadline_does_not_signal(tmp_path: Path, value: object) -> None:
    literal = "float('nan')" if isinstance(value, float) and value != value else repr(value)
    if literal == "inf":
        literal = "float('inf')"
    _drive(
        tmp_path,
        "scope=Scope(left)\n"
        f"try: scope.stop(timeout_seconds={literal})\n"
        "except Error as exc: assert 'deadline' in str(exc)\n"
        "else: raise AssertionError('Invalid stop deadline accepted')\n"
        "scope.require_live();scope.stop(timeout_seconds=2);scope.close()",
    )


def test_linux_scope_live_close_cannot_claim_completion(tmp_path: Path) -> None:
    _drive(
        tmp_path,
        "scope=Scope(left)\n"
        "try: scope.close()\n"
        "except Error: pass\n"
        "else: raise AssertionError('Live scope handles released')\n"
        "scope.require_live();scope.stop(timeout_seconds=2);scope.close()",
    )
