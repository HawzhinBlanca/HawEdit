"""Real original worker namespace/root transitions; no copied runtime admission."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_linux_prepared_view import DRIVER, INIT
from test_linux_scope import _execute, _source


def _replace(program: str, old: str, new: str) -> str:
    assert program.count(old) == 1
    return program.replace(old, new)


def _drive_joined(tmp_path: Path, *, fault: str = "none", action: str = "") -> None:
    init = _replace(
        INIT,
        "worker=os.fork()",
        "sync=socket.socket(fileno=int(sys.argv[4]))\n"
        "wp,wc=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)\n"
        "worker=os.fork()",
    )
    init = _replace(
        init,
        " time.sleep(9);os._exit(99)",
        r"""
 wp.close()
 packet,ancillary,flags,address=wc.recvmsg(1,socket.CMSG_SPACE(12),socket.MSG_CMSG_CLOEXEC)
 assert packet==b'V' and len(ancillary)==1
 rights=array.array('i');rights.frombytes(ancillary[0][2]);assert len(rights)==3
 user,mnt,root_fd=rights
 assert libc.setns(user,0x10000000)==0,ctypes.get_errno()
 if JOIN_FAULT!='skip_mount':assert libc.setns(mnt,0x20000)==0,ctypes.get_errno()
 if JOIN_FAULT=='new_mount':assert libc.unshare(0x20000)==0,ctypes.get_errno()
 if JOIN_FAULT!='skip_root':
  os.fchdir(root_fd);os.chroot('.');os.chdir('/')
 if JOIN_FAULT=='subdir_cwd':os.chdir('/subdir')
 if JOIN_FAULT!='retained_bounding':
  for capability in range(41):assert libc.prctl(24,capability,0,0,0)==0
 if JOIN_FAULT!='retained_effective':
  assert libc.capset(ctypes.byref(Header(0x20080522,0)),(Data*2)())==0
 for fd in rights:os.close(fd)
 if JOIN_FAULT=='threads':
  ready=threading.Event()
  def waiting():ready.set();time.sleep(9)
  threading.Thread(target=waiting).start();assert ready.wait(1)
 wc.send(b'D')
 if JOIN_FAULT=='exit':os._exit(0)
 if JOIN_FAULT=='traced':assert libc.ptrace(0,0,None,None)==0
 if JOIN_FAULT!='running':os.kill(os.getpid(),signal.SIGSTOP)
 time.sleep(9);os._exit(99)
""",
    )
    init = _replace(
        init,
        "\ntime.sleep(9)\n",
        "\nwc.close()\nassert prepared.recv(1)==b'J'\n"
        "wp.sendmsg([b'V'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[user,mnt,root_fd]))])\n"
        "os.kill(worker,signal.SIGCONT)\nassert wp.recv(1)==b'D'\n"
        "if JOIN_FAULT!='running':\n"
        " status=os.waitpid(worker,os.WUNTRACED)[1]\n"
        " assert (os.WIFEXITED(status) if JOIN_FAULT=='exit' else os.WIFSTOPPED(status)),status\n"
        "sync.send(b'H')\ntime.sleep(9)\n",
    )
    driver = _replace(
        DRIVER,
        "pl,pr=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)",
        "pl,pr=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)\n"
        "jl,jr=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)",
    )
    driver = _replace(
        driver,
        "str(right.fileno()),str(pr.fileno()),str(root)],pass_fds=(right.fileno(),pr.fileno()),",
        "str(right.fileno()),str(pr.fileno()),str(root),str(jr.fileno())],"
        "pass_fds=(right.fileno(),pr.fileno(),jr.fileno()),",
    )
    driver = _replace(driver, "right.close();pr.close()", "right.close();pr.close();jr.close()")
    driver = _replace(
        driver,
        "os.close(original_manager);left.close();pl.close()",
        "os.close(original_manager);left.close();pl.close();jl.close()",
    )
    if not action:
        action = (
            "view.verify_joined()"
            if fault == "none"
            else "try:view.verify_joined()\nexcept Error:pass\n"
            "else:raise AssertionError('Damaged original transition admitted')\n"
            "try:view.verify_joined()\nexcept Error:pass\n"
            "else:raise AssertionError('Transition uncertainty erased')"
        )
    body = (
        "scope=Scope(left);view=View(scope,pl);left.send(b'G')\n"
        "view.observe_prepared(timeout_seconds=2);view.verify_prepared()\n"
        "pl.send(b'J');assert select.select([jl],[],[],2)[0];assert jl.recv(1)==b'H'\n" + action
    )
    code = (
        driver.replace("SOURCE", repr(_source()))
        .replace(
            "INIT_PROGRAM", repr(init.replace("JOIN_FAULT", repr(fault)).replace("FAULT", "'none'"))
        )
        .replace("  ACTION", "\n".join("  " + line for line in body.splitlines()))
    )
    result = _execute(tmp_path, code)
    status = getattr(result, "exit_code", getattr(result, "returncode", None))
    assert status == 0, result.stderr.decode("utf-8", "replace")
    assert json.loads(result.stdout) == {"observed": True}


def test_rooted_launch_owner_reobserves_joined_original_worker(tmp_path: Path) -> None:
    _drive_joined(tmp_path)


@pytest.mark.parametrize(
    "fault",
    [
        "skip_mount",
        "new_mount",
        "skip_root",
        "subdir_cwd",
        "retained_bounding",
        "retained_effective",
        "threads",
        "running",
        "exit",
        "traced",
    ],
)
def test_rooted_launch_joined_worker_damaged_transition_refuses(tmp_path: Path, fault: str) -> None:
    _drive_joined(tmp_path, fault=fault)


def test_rooted_launch_joined_observation_has_no_execution_authority(tmp_path: Path) -> None:
    _drive_joined(
        tmp_path,
        action="before=set(os.listdir('/proc/self/fd'))\n"
        "for iteration in range(10):assert view.verify_joined() is None\n"
        "assert set(os.listdir('/proc/self/fd'))==before\n"
        "with open('/proc/'+str(view._ids[1][0])+'/status') as stream:\n"
        " fields=dict(line.split(':',1) for line in stream if ':' in line)\n"
        "assert fields['State'].strip().startswith('T (')\n"
        "assert fields['TracerPid'].strip()=='0'",
    )


def test_rooted_launch_joined_observation_requires_actual_transition(tmp_path: Path) -> None:
    from test_linux_prepared_view import _drive_view

    _drive_view(
        tmp_path,
        action="view.observe_prepared(timeout_seconds=2)\n"
        "try:view.verify_joined()\nexcept Error:pass\n"
        "else:raise AssertionError('Unjoined worker admitted')",
    )


def test_rooted_launch_joined_observation_requires_authenticated_handoff(tmp_path: Path) -> None:
    from test_linux_prepared_view import _drive_view

    _drive_view(
        tmp_path,
        action="try:view.verify_joined()\nexcept Error:pass\n"
        "else:raise AssertionError('Missing prepared handoff accepted')\n"
        "view.observe_prepared(timeout_seconds=2);view.verify_prepared()",
    )


@pytest.mark.parametrize("slot", ["primary", "anchor", "witness"])
def test_rooted_launch_joined_observation_preserves_substituted_description(
    tmp_path: Path, slot: str
) -> None:
    _drive_joined(
        tmp_path,
        action="view.verify_joined()\n"
        "prepared_root=view._prepared[2]\n"
        f"slot={slot!r}\n"
        "target=prepared_root if slot=='primary' else "
        "view._owned[prepared_root][0 if slot=='anchor' else 1]\n"
        "foreign=os.open('/proc/self/fd/'+str(prepared_root),"
        "os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)\n"
        "os.dup2(foreign,target,inheritable=False)\n"
        "try:view.verify_joined()\nexcept Error:pass\n"
        "else:raise AssertionError('Reopened description admitted')\n"
        "try:view.close()\nexcept Error:pass\n"
        "else:raise AssertionError('Uncertain custody reported closed')\n"
        "assert fcntl.fcntl(target,1027,foreign)==1\n"
        "os.close(target);os.close(foreign)",
    )


def test_rooted_launch_joined_observation_refuses_dead_original_scope(tmp_path: Path) -> None:
    _drive_joined(
        tmp_path,
        action="view.verify_joined();scope.stop(timeout_seconds=2);scope.close()\n"
        "try:view.verify_joined()\nexcept Error:pass\n"
        "else:raise AssertionError('Dead original scope admitted')",
    )
