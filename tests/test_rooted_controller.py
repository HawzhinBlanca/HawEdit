"""Real typed Snapshot controller; no ASR/model admission from these diagnostics."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from test_linux_prepared_view import DRIVER
from test_linux_scope import _execute, _source
from test_rooted_worker import INIT


def _controller_run(tmp_path: Path, case: str) -> None:
    from hawedit.wsl_setup import wsl_path

    package = (
        wsl_path(Path(__file__).parents[1] / "src", executable="C:/Program Files/WSL/wsl.exe")
        if os.name == "nt"
        else str(Path(__file__).parents[1] / "src")
    )
    prefix = INIT.split("snapshot=LinuxSnapshot(root,files", 1)[0]
    prefix = prefix.replace("PACKAGE", repr(package)).replace(
        "CASE", repr("python" if case != "elf" else "none")
    )
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
try:
 snapshot=LinuxSnapshot(root,files,mode=SnapshotMode.ROOTED_IMAGE,
  kernel_entropy=True,max_bytes=maximum,launch=launch)
except Exception as exc:
 if TEST_CASE not in ('overflow','timeout','manifest','owner_eof'):raise
 expected={'overflow':'output','timeout':'deadline','manifest':'manifest','owner_eof':'owner'}[TEST_CASE]
 assert expected in str(exc.__cause__).lower(),repr(exc.__cause__)
 assert launch.result is None
 if TEST_CASE=='manifest':
  import hawedit.linux_snapshot as state
  assert state._ATTEMPTED is False and not tuple(root.iterdir())
  signal.pidfd_send_signal(original,signal.SIGKILL);os.waitpid(2,0)
 assert select.select([original],[],[],0)[0]
else:
 assert TEST_CASE not in ('overflow','timeout','manifest','owner_eof'),'Refusal reported success'
 result=launch.result;assert result is not None
 assert result.exit_code==(42 if TEST_CASE=='elf' else 0)
 assert result.exec_count==1 and result.observed_tids==result.reaped_tids==(2,)
 if TEST_CASE=='python':
  assert json.loads(result.output)=={'version':'3.12.0','nnP':'1','caps_zero':True}
 snapshot.verify();snapshot.close()
time.sleep(9)
"""
    )
    init = init.replace("TEST_CASE", repr(case))
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
    if case == "manifest":
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
