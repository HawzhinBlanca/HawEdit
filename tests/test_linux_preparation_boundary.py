"""Real original stopped-worker preparation checks, not execution admission."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from test_linux_scope import DRIVER, PRELUDE, _execute, _source

INIT = (
    PRELUDE
    + r"""
assert os.getpid()==1
channel=socket.socket(fileno=int(sys.argv[1]))
request=channel.recv(64);assert request[:4]==b'HEA1' and len(request)==36
nonce=request[4:]
class Header(ctypes.Structure):
 _fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
class Data(ctypes.Structure):
 _fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
def initial_boundary(worker=False):
 assert libc.capset(ctypes.byref(Header(0x20080522,0)),(Data*2)())==0
 if not (worker and FAULT=='worker_nnp'):
  assert libc.prctl(38,1,0,0,0)==0
 with open('/proc/self/status') as stream:
  status=dict(line.split(':',1) for line in stream if ':' in line)
 assert int(status['CapBnd'],16)!=0
if FAULT in ('pid3','extra'):
 extra=os.fork()
 if extra==0:
  signal.pause();os._exit(99)
worker=os.fork()
if worker==0:
 initial_boundary(worker=True)
 if FAULT=='threads':
  ready=threading.Event()
  def waiting():
   ready.set();time.sleep(9)
  threading.Thread(target=waiting).start();assert ready.wait(1)
 os.kill(os.getpid(),signal.SIGSTOP)
 time.sleep(9);os._exit(99)
assert os.waitpid(worker,os.WUNTRACED)[1]==signal.SIGSTOP*256+127
initial_boundary()
held=[pidfd(1),os.open('/proc/self/ns/pid',os.O_RDONLY|os.O_CLOEXEC),
 os.open('/proc/self/ns/user',os.O_RDONLY|os.O_CLOEXEC),pidfd(worker)]
if FAULT=='extra':held.append(pidfd(extra))
packet=b'HES1'+nonce+struct.pack('!I',len(held))
channel.sendmsg([packet],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',held))])
channel.shutdown(socket.SHUT_WR)
assert channel.recv(1)==b'G'
if FAULT=='running':
 os.kill(worker,signal.SIGCONT)
 time.sleep(.05)
if FAULT=='transitioned':
 assert libc.unshare(0x10000000)==0
if FAULT=='capabilities':
 assert libc.unshare(0x10000000)==0
 with open('/proc/self/status') as stream:
  values=dict(line.split(':',1) for line in stream if ':' in line)
 assert int(values['CapEff'],16)!=0 and int(values['CapPrm'],16)!=0
if FAULT=='mount':
 original=os.stat('/proc/self/ns/mnt')
 assert libc.unshare(0x10020000)==0
 current=os.stat('/proc/self/ns/mnt')
 assert (current.st_dev,current.st_ino)!=(original.st_dev,original.st_ino)
os.write(int(sys.argv[2]),b'R')
time.sleep(9)
"""
)


def _drive_boundary(tmp_path: Path, *, fault: str = "none", action: str = "") -> None:
    source = _source()
    if not action:
        action = (
            "scope.require_preparation_ready()\nscope.require_preparation_ready()"
            if fault == "none"
            else "try:scope.require_preparation_ready()\n"
            "except Error:pass\n"
            "else:raise AssertionError('Invalid preparation boundary admitted')"
        )
    body = (
        "scope=Scope(left);scope.require_live();left.send(b'G')\n"
        "assert select.select([ack_read],[],[],2)[0] and os.read(ack_read,1)==b'R'\n"
        + action
        + "\nif not scope._closed:scope.stop(timeout_seconds=2);scope.close()"
    )
    code = (
        DRIVER.replace("SOURCE", repr(source))
        .replace("INIT_PROGRAM", repr(INIT.replace("FAULT", repr(fault))))
        .replace(" ACTION", "\n".join(" " + line for line in body.splitlines()))
    )
    result = _execute(tmp_path, code)
    status = getattr(result, "exit_code", getattr(result, "returncode", None))
    assert status == 0, result.stderr.decode("utf-8", "replace")
    assert json.loads(result.stdout) == {"observed": True}


def test_rooted_launch_original_owner_precedes_preparation(tmp_path: Path) -> None:
    _drive_boundary(tmp_path)


@pytest.mark.parametrize(
    "fault",
    ["capabilities", "worker_nnp", "mount", "pid3", "extra", "threads", "running", "transitioned"],
)
def test_rooted_launch_invalid_preparation_boundary_refuses(tmp_path: Path, fault: str) -> None:
    _drive_boundary(tmp_path, fault=fault)


def test_rooted_launch_preparation_has_no_release_authority(tmp_path: Path) -> None:
    _drive_boundary(
        tmp_path,
        action="assert scope.require_preparation_ready() is None\n"
        "with open('/proc/'+str(ns['_pid_info'](scope._anchors[3])[0])+'/status') as stream:\n"
        " assert 'State:\\tT' in stream.read()",
    )


def test_rooted_launch_preparation_refuses_closed_scope(tmp_path: Path) -> None:
    _drive_boundary(
        tmp_path,
        action="scope.stop(timeout_seconds=2);scope.close()\n"
        "try:scope.require_preparation_ready()\n"
        "except Error:pass\n"
        "else:raise AssertionError('Closed scope admitted preparation')",
    )


def test_rooted_launch_preparation_api_is_explicit() -> None:
    scope = importlib.import_module("hawedit.linux_scope").LinuxScope
    assert callable(getattr(scope, "require_preparation_ready", None))


@pytest.mark.parametrize(
    "value", [True, False, None, "5", 0, -1, float("nan"), float("inf"), 31, 43201]
)
def test_rooted_launch_preparation_invalid_deadline_refuses(value: object) -> None:
    module = importlib.import_module("hawedit.linux_scope")
    with pytest.raises(module.LinuxScopeError, match="deadline"):
        module.LinuxScope.require_preparation_ready(None, timeout_seconds=value)


def test_rooted_launch_preparation_refuses_multithread_creator(tmp_path: Path) -> None:
    _drive_boundary(
        tmp_path,
        action="ready=threading.Event();finish=threading.Event()\n"
        "def waiting():ready.set();finish.wait(2)\n"
        "thread=threading.Thread(target=waiting);thread.start();assert ready.wait(1)\n"
        "try:scope.require_preparation_ready()\n"
        "except Error:pass\n"
        "else:raise AssertionError('Concurrent creator admitted preparation')\n"
        "finally:finish.set();thread.join(2)\n"
        "assert not thread.is_alive()",
    )


def test_rooted_launch_preparation_retains_bounding_caps_without_fd_leaks(tmp_path: Path) -> None:
    _drive_boundary(
        tmp_path,
        action="before=set(os.listdir('/proc/self/fd'))\n"
        "for iteration in range(10):scope.require_preparation_ready()\n"
        "assert set(os.listdir('/proc/self/fd'))==before",
    )
