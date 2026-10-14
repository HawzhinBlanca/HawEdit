"""Real typed Snapshot controller; no ASR/model admission from these diagnostics."""

from __future__ import annotations

import ast
import json
import os
import socket
from pathlib import Path

import pytest

from test_linux_prepared_view import DRIVER
from test_linux_scope import _execute, _source
from test_rooted_worker import INIT

COMM_PROBE = """
import errno,json,os,threading
ready=threading.Event();finish=threading.Event();tids=[]
def wait_for_finish():
 tids.append(threading.get_native_id());ready.set();assert finish.wait(5)
thread=threading.Thread(target=wait_for_finish);thread.start();assert ready.wait(2)
try:
 with open('/proc/self/task/'+str(tids[0])+'/comm','w') as stream:
  assert stream.write('HawEditOriginal')==15
 with open('/proc/self/task/'+str(tids[0])+'/comm') as stream:
  measured=stream.read().strip()
 assert measured=='HawEditOriginal'
 try:
  with open('/proc/self/task/1/comm','w') as stream:stream.write('Forbidden')
 except OSError as exc:assert exc.errno==errno.EPERM
 else:raise AssertionError('Foreign thread-name write admitted')
 try:fd=os.open('/dev/urandom',os.O_RDWR|os.O_CLOEXEC)
 except OSError as exc:
  denied=exc.errno;assert denied==(errno.EACCES if GPU else errno.EPERM)
 else:os.close(fd);raise AssertionError('Entropy write admitted')
 device=None
 if GPU:
  fd=os.open('/dev/dxg',os.O_RDWR|os.O_CLOEXEC)
  try:
   info=os.fstat(fd);device=[os.major(info.st_rdev),os.minor(info.st_rdev)]
   assert device==[10,258]
  finally:os.close(fd)
 print(json.dumps({'comm':measured,'tid':tids[0],'entropy_errno':denied,'device':device}))
finally:
 finish.set();thread.join(2);assert not thread.is_alive()
"""


def _controller_run(tmp_path: Path, case: str) -> None:
    from hawedit.wsl_setup import wsl_path

    package = (
        wsl_path(Path(__file__).parents[1] / "src", executable="C:/Program Files/WSL/wsl.exe")
        if os.name == "nt"
        else str(Path(__file__).parents[1] / "src")
    )
    prefix = INIT.split("snapshot=LinuxSnapshot(root,files", 1)[0]
    prefix = prefix.replace("PACKAGE", repr(package)).replace(
        "CASE",
        repr("none" if case in ("elf", "gpu_elf", "gpu_mismatch", "task_reopen") else "python"),
    )
    gpu = case.startswith("gpu_")
    if gpu:
        prefix = prefix.replace(
            "command=RootedCommand(files,executable,arguments,environment)",
            "command=RootedCommand(files,executable,arguments,environment,wsl_gpu=True)",
        )
        prefix = prefix.replace("original=held[3]", "original=held[3]\nchannel.close()")
    if case in ("comm", "gpu_comm"):
        tree = ast.parse(prefix)
        writes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "probe"
            and node.func.attr == "write_text"
        ]
        assert len(writes) == 1
        writes[0].args[0] = ast.Constant(COMM_PROBE.replace("GPU", repr(gpu)))
        prefix = ast.unparse(ast.fix_missing_locations(tree))
    if case in ("comm", "gpu_comm"):
        start = prefix.index("wp, wc = socket.socketpair")
        finish = prefix.index("held = [pidfd(1)")
    else:
        start = prefix.index("wp,wc=socket.socketpair")
        finish = prefix.index("held=[pidfd(1)")
    prefix = (
        prefix[:start]
        + """
from hawedit.linux_rooted_launch import RootedLaunch
os.set_inheritable(prepared.fileno(),False)
launch=RootedLaunch(command,prepared,output_limit_bytes=1024,
 timeout_seconds=.2 if TEST_CASE=='timeout' else 30)
worker=2
"""
        + prefix[finish:]
    )
    prefix = prefix.replace("pidfd(worker)]", "launch.worker_pidfd]")
    if case == "overflow":
        prefix = prefix.replace(
            "print(json.dumps({'version':sys.version.split()[0],'nnP':fields['NoNewPrivs'].strip(),'caps_zero':True}))",
            "print('X'*4096)",
        )
    if case == "timeout":
        prefix = prefix.replace(
            "print(json.dumps({'version':sys.version.split()[0],'nnP':fields['NoNewPrivs'].strip(),'caps_zero':True}))",
            "__import__('time').sleep(2)",
        )
    init = (
        prefix
        + """
if TEST_CASE=='manifest':
 first=files[0]
 files=(SnapshotFile(first.source,first.relative_path,'0'*64,first.size_bytes,first.executable),*files[1:])
if TEST_CASE=='task_reopen':
 reopened=os.open('/proc/2/task',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
 os.dup2(reopened,launch._task,inheritable=False);os.close(reopened)
refusals=('overflow','timeout','manifest','owner_eof','gpu_mismatch','task_reopen')
try:
 snapshot=LinuxSnapshot(root,files,mode=SnapshotMode.ROOTED_IMAGE,
  kernel_entropy=True,max_bytes=maximum,launch=launch,
  wsl_gpu=GPU_ENABLED and TEST_CASE!='gpu_mismatch')
except Exception as exc:
 if TEST_CASE not in refusals:raise
 expected={'overflow':'output','timeout':'deadline','manifest':'manifest','owner_eof':'owner',
  'gpu_mismatch':'manifest','task_reopen':'description'}[TEST_CASE]
 assert expected in str(exc.__cause__).lower(),repr(exc.__cause__)
 assert launch.result is None
 if TEST_CASE in ('manifest','gpu_mismatch','task_reopen'):
  import hawedit.linux_snapshot as state
  assert state._ATTEMPTED is False and not tuple(root.iterdir())
  if TEST_CASE=='task_reopen':
   import fcntl
   assert os.fstat(launch._task).st_ino==os.fstat(launch._held[-1].anchor).st_ino
   assert fcntl.fcntl(launch._task,1027,launch._held[-1].anchor)==0
  signal.pidfd_send_signal(original,signal.SIGKILL);os.waitpid(2,0)
 assert select.select([original],[],[],0)[0]
else:
 assert TEST_CASE not in refusals,'Refusal reported success'
 result=launch.result;assert result is not None
 assert result.exit_code==(42 if TEST_CASE in ('elf','gpu_elf') else 0)
 expected_tids=(2,3) if TEST_CASE in ('comm','gpu_comm') else (2,)
 assert result.exec_count==1 and result.observed_tids==result.reaped_tids==expected_tids
 assert type(snapshot._controller_filters) is int
 assert snapshot._filters>snapshot._controller_filters>0
 if TEST_CASE=='python':
  assert json.loads(result.output)=={'version':'3.12.0','nnP':'1','caps_zero':True}
 if TEST_CASE in ('comm','gpu_comm'):
  assert json.loads(result.output)=={'comm':'HawEditOriginal','tid':3,
   'entropy_errno':13 if GPU_ENABLED else 1,'device':[10,258] if GPU_ENABLED else None}
 snapshot.verify();snapshot.close()
time.sleep(9)
"""
    )
    init = init.replace("TEST_CASE", repr(case)).replace("GPU_ENABLED", repr(gpu))
    action = """
scope=Scope(left,timeout_seconds=30);view=View(scope,pl);left.send(b'G')
view.observe_prepared(timeout_seconds=30);view.verify_prepared()
original_signal(scope._anchors[3],signal.SIGCONT);pl.send(b'J')
end=time.monotonic()+3
while True:
 with open('/proc/'+str(view._ids[1][0])+'/status') as stream:
  fields=dict(line.split(':',1) for line in stream if ':' in line)
 joined=os.readlink('/proc/'+str(view._ids[1][0])+'/ns/mnt')==os.readlink('/proc/'+str(view._ids[0][0])+'/ns/mnt')
 if joined and fields['State'].strip().startswith('T ('):break
 assert time.monotonic()<end;time.sleep(.001)
view.verify_joined()
original_signal(scope._anchors[3],signal.SIGCONT);pl.send(b'R')
assert select.select([scope._anchors[3]],[],[],5)[0]
time.sleep(.1)
"""
    if case in ("manifest", "gpu_mismatch", "task_reopen"):
        action = (
            "scope=Scope(left,timeout_seconds=30);left.send(b'G')\n"
            "assert select.select([scope._anchors[3]],[],[],5)[0]\ntime.sleep(.1)"
        )
    if case == "owner_eof":
        action = action.replace(
            "original_signal(scope._anchors[3],signal.SIGCONT);pl.send(b'R')",
            "pl.shutdown(socket.SHUT_WR)",
        )
    driver = DRIVER.replace("SOURCE", repr(_source())).replace("INIT_PROGRAM", repr(init))
    if gpu:
        driver = driver.replace("stderr=subprocess.PIPE)", "stderr=subprocess.DEVNULL)")
        driver = driver.replace(
            "assert manager.stderr is not None;diagnostic=manager.stderr.read();"
            "manager.stderr.close()",
            "assert manager.stderr is None;diagnostic=b''",
        )
    driver = driver.replace("  ACTION", "\n".join("  " + line for line in action.splitlines()))
    result = _execute(tmp_path, driver)
    assert getattr(result, "exit_code", getattr(result, "returncode", None)) == 0, (
        result.stderr.decode("utf-8", "replace")
    )
    assert json.loads(result.stdout) == {"observed": True}


def test_rooted_controller_actual_elf_returns_fenced(tmp_path: Path) -> None:
    _controller_run(tmp_path, "elf")


def test_rooted_controller_actual_python_returns_bounded_output(tmp_path: Path) -> None:
    _controller_run(tmp_path, "python")


def test_rooted_controller_actual_cpu_comm_service_returns_fenced(tmp_path: Path) -> None:
    _controller_run(tmp_path, "comm")


def test_rooted_controller_actual_gpu_comm_service_returns_fenced(tmp_path: Path) -> None:
    _controller_run(tmp_path, "gpu_comm")


def test_rooted_controller_actual_gpu_elf_returns_fenced(tmp_path: Path) -> None:
    _controller_run(tmp_path, "gpu_elf")


def test_rooted_controller_gpu_declaration_mismatch_refuses_before_copy(tmp_path: Path) -> None:
    _controller_run(tmp_path, "gpu_mismatch")


def test_rooted_controller_reopened_original_task_inode_refuses_before_copy(tmp_path: Path) -> None:
    _controller_run(tmp_path, "task_reopen")


def test_rooted_controller_final_filter_binds_original_installed_profile(tmp_path: Path) -> None:
    _controller_run(tmp_path, "elf")


def test_rooted_controller_output_overflow_drains_and_refuses(tmp_path: Path) -> None:
    _controller_run(tmp_path, "overflow")


def test_rooted_controller_timeout_drains_and_refuses(tmp_path: Path) -> None:
    _controller_run(tmp_path, "timeout")


def test_rooted_controller_manifest_refuses_before_copy(tmp_path: Path) -> None:
    _controller_run(tmp_path, "manifest")


def test_rooted_controller_owner_eof_refuses_before_exec(tmp_path: Path) -> None:
    _controller_run(tmp_path, "owner_eof")


@pytest.mark.parametrize("limit", [0, -1, True, 65537, float("inf")])
def test_rooted_controller_invalid_declarations_refuse(tmp_path: Path, limit: object) -> None:
    from hawedit.linux_rooted_launch import RootedLaunch
    from hawedit.linux_rooted_worker import RootedCommand
    from hawedit.linux_snapshot import LinuxSnapshotError, SnapshotFile

    command = RootedCommand((SnapshotFile(tmp_path / "tool", "tool", "0" * 64, 1, True),), "tool")
    with socket.socket() as channel, pytest.raises(LinuxSnapshotError, match="declaration"):
        RootedLaunch(command, channel, output_limit_bytes=limit)  # type: ignore[arg-type]


@pytest.mark.parametrize("seconds", [0, -1, True, 30.1, float("nan"), float("inf")])
def test_rooted_controller_invalid_deadlines_refuse(tmp_path: Path, seconds: object) -> None:
    from hawedit.linux_rooted_launch import RootedLaunch
    from hawedit.linux_rooted_worker import RootedCommand
    from hawedit.linux_snapshot import LinuxSnapshotError, SnapshotFile

    command = RootedCommand((SnapshotFile(tmp_path / "tool", "tool", "0" * 64, 1, True),), "tool")
    with socket.socket() as channel, pytest.raises(LinuxSnapshotError, match="declaration"):
        RootedLaunch(command, channel, timeout_seconds=seconds)  # type: ignore[arg-type]


def test_rooted_controller_gpu_is_not_silently_downgraded(tmp_path: Path) -> None:
    from hawedit.linux_rooted_launch import RootedLaunch
    from hawedit.linux_rooted_worker import RootedCommand
    from hawedit.linux_snapshot import LinuxSnapshotError, SnapshotFile

    command = RootedCommand(
        (SnapshotFile(tmp_path / "tool", "tool", "0" * 64, 1, True),), "tool", wsl_gpu=True
    )
    with socket.socket() as channel, pytest.raises(LinuxSnapshotError, match="GPU"):
        RootedLaunch(command, channel)


def test_rooted_command_valid_declaration_is_portable_without_consuming_bytes(
    tmp_path: Path,
) -> None:
    from hawedit.linux_rooted_worker import RootedCommand
    from hawedit.linux_snapshot import SnapshotFile

    absent = tmp_path / "not-consumed"
    command = RootedCommand((SnapshotFile(absent, "bin/tool", "0" * 64, 132, True),), "bin/tool")
    assert command.executable == "bin/tool"
    assert command.files[0].source == absent
    assert not absent.exists()
