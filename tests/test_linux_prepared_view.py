"""Actual original prepared namespace/root witnesses, not copied SDK admission."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from test_linux_scope import PRELUDE, _execute, _source

INIT = (
    PRELUDE
    + r"""
assert os.getpid()==1
channel=socket.socket(fileno=int(sys.argv[1]))
prepared=socket.socket(fileno=int(sys.argv[2]))
root=sys.argv[3]
request=channel.recv(64);assert request[:4]==b'HEA1' and len(request)==36
class Header(ctypes.Structure):
 _fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
class Data(ctypes.Structure):
 _fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
assert libc.capset(ctypes.byref(Header(0x20080522,0)),(Data*2)())==0
assert libc.prctl(38,1,0,0,0)==0
worker=os.fork()
if worker==0:
 os.kill(os.getpid(),signal.SIGSTOP)
 time.sleep(9);os._exit(99)
assert os.waitpid(worker,os.WUNTRACED)[1]==signal.SIGSTOP*256+127
held=[pidfd(1),os.open('/proc/self/ns/pid',os.O_RDONLY|os.O_CLOEXEC),
 os.open('/proc/self/ns/user',os.O_RDONLY|os.O_CLOEXEC),pidfd(worker)]
channel.sendmsg([b'HES1'+request[4:]+struct.pack('!I',4)],
 [(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',held))])
channel.shutdown(socket.SHUT_WR)
assert channel.recv(1)==b'G'
original_user=os.open('/proc/self/ns/user',os.O_RDONLY|os.O_CLOEXEC)
original_mount=os.open('/proc/self/ns/mnt',os.O_RDONLY|os.O_CLOEXEC)
original_root=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
uid,gid=os.getuid(),os.getgid()
assert libc.unshare(0x10020000)==0
with open('/proc/self/setgroups','w') as stream:stream.write('deny')
with open('/proc/self/uid_map','w') as stream:stream.write(f'{uid} {uid} 1')
with open('/proc/self/gid_map','w') as stream:stream.write(f'{gid} {gid} 1')
assert (os.getuid(),os.getgid())==(uid,gid)
libc.mount.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_ulong,ctypes.c_void_p]
def mount(source,target,kind,flags,data=None):
 assert libc.mount(source,target,kind,flags,data)==0,(ctypes.get_errno(),target)
mount(None,b'/',None,(1<<18)|(1<<14))
mount(b'tmpfs',os.fsencode(root),b'tmpfs',2|4,b'size=1048576,mode=0700')
os.mkdir(root+'/proc',0o700);os.mkdir(root+'/subdir',0o700)
if FAULT!='fakeproc':
 mount(b'/proc',os.fsencode(root+'/proc'),None,4096|16384)
 if FAULT!='proc_rw':mount(None,os.fsencode(root+'/proc'),None,32|4096|1|2|4|8)
user=os.open('/proc/self/ns/user',os.O_RDONLY|os.O_CLOEXEC)
mnt=os.open('/proc/self/ns/mnt',os.O_RDONLY|os.O_CLOEXEC)
root_fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
if FAULT!='root_rw':mount(None,os.fsencode(root),None,32|1|2|4)
if FAULT=='cwd_foreign':os.chroot(root)
elif FAULT!='no_chroot':os.chdir(root);os.chroot('.');os.chdir('/')
if FAULT=='worker_running':os.kill(worker,signal.SIGCONT);time.sleep(.05)
if FAULT=='worker_exit':os.kill(worker,signal.SIGKILL);os.waitpid(worker,0)
if FAULT=='init_threads':
 ready=threading.Event()
 def waiting():ready.set();time.sleep(9)
 threading.Thread(target=waiting).start();assert ready.wait(1)
 with open('/proc/self/status') as stream:
  fields=dict(line.split(':',1) for line in stream if ':' in line)
 assert fields['Threads'].strip()=='2'
request=prepared.recv(64);assert request[:4]==b'HEQ1' and len(request)==36
rights=[user,mnt,root_fd]
if FAULT=='user_original':rights[0]=original_user
if FAULT=='mount_original':rights[1]=original_mount
if FAULT=='root_foreign':rights[2]=original_root
if FAULT=='root_subdir':
 rights[2]=os.open('subdir',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=root_fd)
if FAULT=='wrong_type':rights[0]=os.dup(root_fd)
if FAULT=='extra_rights':rights.append(os.dup(root_fd))
packet=b'HEP1'+request[4:]
if FAULT=='nonce':packet=b'HEP1'+b'x'*32
if FAULT=='prefix':packet=b'BAD!'+packet[4:]
if FAULT=='short':packet=packet[:-1]
if FAULT=='sender_foreign':
 sender=os.fork()
 if sender!=0:
  os.waitpid(sender,0);time.sleep(9);os._exit(99)
if FAULT!='stalled':
 prepared.sendmsg([packet],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',rights))])
 if FAULT=='duplicate':
  prepared.sendmsg([packet],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',rights))])
 if FAULT=='empty_packet':prepared.send(b'')
 if FAULT!='no_eof':prepared.shutdown(socket.SHUT_WR)
if FAULT=='sender_foreign':os._exit(0)
time.sleep(9)
"""
)

DRIVER = (
    PRELUDE
    + r"""
import tempfile
from pathlib import Path
ns={'__name__':'hawedit_linux_prepared_under_test'}
exec(compile(SOURCE,'linux_scope.py','exec'),ns)
Scope=ns['LinuxScope'];View=ns['LinuxPreparedView'];Error=ns['LinuxScopeError']
left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
pl,pr=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
left.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
pl.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
with tempfile.TemporaryDirectory(prefix='hawedit-prepared-') as base:
 root=Path(base)/'root';root.mkdir(mode=0o700)
 manager=subprocess.Popen(['/usr/bin/unshare','--user','--map-current-user','--pid','--fork',
 '--kill-child=SIGKILL','--mount-proc',sys.executable,'-I','-B','-c',INIT_PROGRAM,
 str(right.fileno()),str(pr.fileno()),str(root)],pass_fds=(right.fileno(),pr.fileno()),
 stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 original_manager=pidfd(manager.pid);right.close();pr.close()
 scope=view=None
 try:
  ACTION
  print(json.dumps({'observed':True}),flush=True)
 finally:
  if view is not None and not view._closed:
   try:view.close()
   except Error:pass
  if scope is not None and not scope._closed and not scope._failed:
   scope.stop(timeout_seconds=2);scope.close()
  if not select.select([original_manager],[],[],0)[0]:
   original_signal(original_manager,signal.SIGKILL)
  assert select.select([original_manager],[],[],4)[0];manager.wait(timeout=1)
  assert manager.stderr is not None;diagnostic=manager.stderr.read();manager.stderr.close()
  assert not diagnostic,diagnostic
  os.close(original_manager);left.close();pl.close()
  assert not tuple(root.iterdir()),'Private namespace mount leaked into creator'
"""
)


def _drive_view(tmp_path: Path, *, fault: str = "none", action: str = "") -> None:
    if not action:
        action = (
            "view.observe_prepared(timeout_seconds=2);view.verify_prepared()"
            if fault == "none"
            else "try:view.observe_prepared(timeout_seconds=.2)\n"
            "except Error:pass\n"
            "else:raise AssertionError('Invalid prepared view admitted')"
        )
    body = "scope=Scope(left);view=View(scope,pl);left.send(b'G')\n" + action
    code = (
        DRIVER.replace("SOURCE", repr(_source()))
        .replace("INIT_PROGRAM", repr(INIT.replace("FAULT", repr(fault))))
        .replace("  ACTION", "\n".join("  " + line for line in body.splitlines()))
    )
    result = _execute(tmp_path, code)
    status = getattr(result, "exit_code", getattr(result, "returncode", None))
    assert status == 0, result.stderr.decode("utf-8", "replace")
    assert json.loads(result.stdout) == {"observed": True}


def test_rooted_launch_owner_reobserves_original_prepared_view(tmp_path: Path) -> None:
    _drive_view(tmp_path)


@pytest.mark.parametrize(
    "fault",
    ["nonce", "prefix", "short", "extra_rights", "duplicate", "empty_packet", "sender_foreign"],
)
def test_rooted_launch_prepared_handoff_framing_refuses(tmp_path: Path, fault: str) -> None:
    _drive_view(tmp_path, fault=fault)


@pytest.mark.parametrize(
    "fault",
    [
        "user_original",
        "mount_original",
        "root_foreign",
        "root_subdir",
        "wrong_type",
        "root_rw",
        "proc_rw",
        "fakeproc",
        "no_chroot",
        "cwd_foreign",
    ],
)
def test_rooted_launch_refuses_foreign_prepared_view(tmp_path: Path, fault: str) -> None:
    _drive_view(tmp_path, fault=fault)


@pytest.mark.parametrize("fault", ["worker_running", "worker_exit", "init_threads"])
def test_rooted_launch_prepared_worker_must_remain_held(tmp_path: Path, fault: str) -> None:
    _drive_view(tmp_path, fault=fault)


@pytest.mark.parametrize("fault", ["stalled", "no_eof"])
def test_rooted_launch_prepared_view_deadline_refuses(tmp_path: Path, fault: str) -> None:
    _drive_view(tmp_path, fault=fault)


def test_rooted_launch_prepared_view_is_not_execution_authority(tmp_path: Path) -> None:
    _drive_view(
        tmp_path,
        action="assert view.observe_prepared(timeout_seconds=2) is None\n"
        "before=set(os.listdir('/proc/self/fd'))\n"
        "for iteration in range(10):assert view.verify_prepared() is None\n"
        "assert set(os.listdir('/proc/self/fd'))==before\n"
        "scope._preparation_member(scope._anchors[3],view._ids[1],"
        "parent=view._ids[0][0],stopped=True)",
    )


@pytest.mark.parametrize("same_inode", [False, True])
@pytest.mark.parametrize("slot", ["primary", "anchor", "witness"])
def test_rooted_launch_prepared_view_preserves_substituted_slots(
    tmp_path: Path, same_inode: bool, slot: str
) -> None:
    _drive_view(
        tmp_path,
        action="view.observe_prepared(timeout_seconds=2)\n"
        "prepared_root=view._prepared[2]\n"
        f"slot={slot!r}\n"
        "primary=prepared_root if slot=='primary' else "
        "view._owned[prepared_root][0 if slot=='anchor' else 1]\n"
        f"path='/proc/self/fd/'+str(prepared_root) if {same_inode!r} else '/tmp'\n"
        "foreign=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)\n"
        "expected=os.fstat(foreign)\n"
        "os.dup2(foreign,primary,inheritable=False)\n"
        "try:view.verify_prepared()\n"
        "except Error:pass\n"
        "else:raise AssertionError('Substituted description accepted')\n"
        "try:view.close()\n"
        "except Error:pass\n"
        "else:raise AssertionError('Uncertain cleanup reported successful')\n"
        "assert os.fstat(primary)==expected\n"
        "assert fcntl.fcntl(primary,1027,foreign)==1\n"
        "os.close(primary);os.close(foreign)",
    )


def test_rooted_launch_prepared_view_refuses_replay(tmp_path: Path) -> None:
    _drive_view(
        tmp_path,
        action="view.observe_prepared(timeout_seconds=2)\n"
        "try:view.observe_prepared(timeout_seconds=2)\n"
        "except Error:pass\n"
        "else:raise AssertionError('Handoff replay accepted')\n"
        "view.verify_prepared()",
    )


def test_rooted_launch_prepared_view_refuses_unobserved_verification(tmp_path: Path) -> None:
    _drive_view(
        tmp_path,
        action="try:view.verify_prepared()\n"
        "except Error:pass\n"
        "else:raise AssertionError('Missing evidence accepted')\n"
        "view.observe_prepared(timeout_seconds=2);view.verify_prepared()",
    )


def test_rooted_launch_prepared_view_refuses_stopped_scope(tmp_path: Path) -> None:
    _drive_view(
        tmp_path,
        action="view.observe_prepared(timeout_seconds=2)\n"
        "scope.stop(timeout_seconds=2);scope.close()\n"
        "try:view.verify_prepared()\n"
        "except Error:pass\n"
        "else:raise AssertionError('Dead original scope accepted')",
    )


def test_rooted_launch_prepared_view_uncertainty_is_sticky(tmp_path: Path) -> None:
    _drive_view(
        tmp_path,
        action="view.observe_prepared(timeout_seconds=2)\n"
        "primary=view._prepared[2];saved=os.dup(primary)\n"
        "foreign=os.open('/tmp',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)\n"
        "os.dup2(foreign,primary,inheritable=False)\n"
        "try:view.verify_prepared()\n"
        "except Error:pass\n"
        "else:raise AssertionError('Foreign slot accepted')\n"
        "os.dup2(saved,primary,inheritable=False)\n"
        "try:view.verify_prepared()\n"
        "except Error:pass\n"
        "else:raise AssertionError('Restoration erased prior uncertainty')\n"
        "os.close(saved);os.close(foreign)",
    )


def test_rooted_launch_prepared_view_partial_anchor_allocation_closes_rights(
    tmp_path: Path,
) -> None:
    _drive_view(
        tmp_path,
        action="import resource\n"
        "def inventory():\n"
        " result={}\n"
        " for name in os.listdir('/proc/self/fd'):\n"
        "  try:result[int(name)]=os.fstat(int(name))\n"
        "  except OSError as exc:assert exc.errno==errno.EBADF\n"
        " return result\n"
        "before=inventory()\n"
        "owned={item for fd,(anchor,witness,identity) in view._owned.items() "
        "for item in (fd,anchor,witness)}\n"
        "free=[fd for fd in range(max(before)+8) if fd not in before]\n"
        "original_limit=resource.getrlimit(resource.RLIMIT_NOFILE)\n"
        "resource.setrlimit(resource.RLIMIT_NOFILE,(free[3]+1,original_limit[1]))\n"
        "try:\n"
        " try:view.observe_prepared(timeout_seconds=2)\n"
        " except Error as exc:\n"
        "  causes=[];cause=exc\n"
        "  while cause is not None:causes.append(cause);cause=cause.__cause__\n"
        "  assert any(isinstance(c,OSError) and c.errno==errno.EMFILE for c in causes)\n"
        " else:raise AssertionError('Actual allocation pressure did not refuse')\n"
        "finally:resource.setrlimit(resource.RLIMIT_NOFILE,original_limit)\n"
        "view.close()\n"
        "after=inventory();expected={fd:info for fd,info in before.items() if fd not in owned}\n"
        "assert after==expected,('extra',set(after)-set(expected),'lost',set(expected)-set(after))",
    )


@pytest.mark.parametrize(
    "value", [True, False, None, "5", 0, -1, float("nan"), float("inf"), 31, 43201]
)
def test_rooted_launch_prepared_view_invalid_deadline_refuses(value: object) -> None:
    module = importlib.import_module("hawedit.linux_scope")
    with pytest.raises(module.LinuxScopeError, match="deadline"):
        module.LinuxPreparedView(None, None, timeout_seconds=value)
