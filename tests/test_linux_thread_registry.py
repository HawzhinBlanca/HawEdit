"""Original birth/custody/lifetime assertions against real Linux kernels."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from original_registry_kernel_probe import program
from test_linux_bootstrap import execute


def observe(tmp_path: Path, case: str) -> dict[str, Any]:
    result = execute(tmp_path, program(case))
    status = getattr(result, "exit_code", getattr(result, "returncode", None))
    assert status == 0, result.stderr.decode("utf-8", "replace")
    record: dict[str, Any] = json.loads(result.stdout)
    assert "error" not in record, record
    assert record["coordinator_exit"] == 0, record
    assert record["readonly_root"] and record["readonly_proc"] and record["root_cleanup"]
    assert record["drained"]
    assert record["observed"] == record["reaped"]
    assert set(record["registered"]) <= set(record["reaped"])
    assert record["kernel"]
    return record


def test_original_registry_anchors_kernel_birth_before_resume(tmp_path: Path) -> None:
    record = observe(tmp_path, "positive")
    assert record["registered"] == [2, 3]
    assert record["event_count_before_use"] >= 3
    assert record["measured_comm"] == "Registered"
    assert record["write_result"] == {"written": 11}
    assert record["injected_fd"] >= 0
    assert record["metadata"]["landlock_abi"] >= 6
    assert record["worker_exit"] == 0


def test_original_registry_refuses_unregistered_or_foreign_target(tmp_path: Path) -> None:
    record = observe(tmp_path, "foreign")
    assert len(record["refusals"]) == 4
    assert record["worker_exit"] == 0


@pytest.mark.parametrize("case", ["substituted", "reopened"])
def test_original_registry_refuses_substituted_task_description(tmp_path: Path, case: str) -> None:
    record = observe(tmp_path, case)
    assert "description" in record["refusal"]
    assert record["foreign_preserved"]
    assert "description" in record["cleanup_refusal"]
    assert record["worker_exit"] == -9
    if case == "reopened":
        assert record["same_inode"]


def test_original_registry_refuses_exited_or_reused_task(tmp_path: Path) -> None:
    record = observe(tmp_path, "stale")
    assert "drained" in record["refusal"]
    assert record["worker_exit"] == -9


def test_original_registry_kernel_refuses_unapproved_trace_requests(tmp_path: Path) -> None:
    record = observe(tmp_path, "trace")
    assert len(record["trace_refusals"]) == 15
    assert all(row["errno"] == 1 for row in record["trace_refusals"])
    assert set(record["metadata"]["worker_refusals"]) == {
        "ptrace",
        "fork",
        "vfork",
        "clone3",
        "process_clone",
        "untraced_clone",
        "ptrace_clone",
    }
    assert record["metadata"]["worker_refusals"] == {
        "ptrace": 1,
        "fork": 1,
        "vfork": 1,
        "clone3": 38,
        "process_clone": 1,
        "untraced_clone": 1,
        "ptrace_clone": 1,
    }


@pytest.mark.parametrize("case", ["budget", "timeout"])
def test_original_registry_drains_all_original_members(tmp_path: Path, case: str) -> None:
    record = observe(tmp_path, case)
    assert record["refusal"]
    assert record["worker_exit"] == -9


@pytest.mark.parametrize("value", [True, None, "5", 0, -1, float("nan"), float("inf"), 31])
def test_original_registry_invalid_deadline_refuses_before_effects(value: object) -> None:
    module = importlib.import_module("hawedit.linux_thread_registry")
    with pytest.raises(module.LinuxThreadRegistryError, match="deadline"):
        module.LinuxThreadRegistry(-1, -1, timeout_seconds=value)


def test_original_registry_anchors_actual_exec_without_state_rewrite(tmp_path: Path) -> None:
    record = observe(tmp_path, "exec")
    assert record["registered"] == [2]
    assert record["exec_count"] == 1
    assert record["worker_exit"] == 42


def test_original_registry_drains_burst_threads_from_kernel_births(tmp_path: Path) -> None:
    record = observe(tmp_path, "many")
    assert record["registered"] == list(range(2, 11))
    assert record["worker_exit"] == 0


@pytest.mark.parametrize("value", [True, None, "5", 0, -1, 65])
def test_original_registry_invalid_thread_budget_refuses_before_effects(value: object) -> None:
    module = importlib.import_module("hawedit.linux_thread_registry")
    with pytest.raises(module.LinuxThreadRegistryError, match="budget"):
        module.LinuxThreadRegistry(-1, -1, max_threads=value)


def test_original_registry_cannot_admit_host_controller(tmp_path: Path) -> None:
    result = execute(
        tmp_path,
        """
from hawedit.linux_thread_registry import LinuxThreadRegistry,LinuxThreadRegistryError
before=set(os.listdir('/proc/self/fd'))
try:LinuxThreadRegistry(-1,-1)
except LinuxThreadRegistryError as exc:assert 'PID1' in str(exc)
else:raise AssertionError('host controller admitted')
assert set(os.listdir('/proc/self/fd')) == before
print(json.dumps({'refused':True}),flush=True)
""",
    )
    status = getattr(result, "exit_code", getattr(result, "returncode", None))
    assert status == 0, result.stderr.decode("utf-8", "replace")
    assert json.loads(result.stdout) == {"refused": True}


def test_original_registry_closed_task_slot_is_not_close_authority(tmp_path: Path) -> None:
    record = observe(tmp_path, "closed")
    assert "custody" in record["refusal"]
    assert "description" in record["cleanup_refusal"]
    assert record["worker_exit"] == -9
