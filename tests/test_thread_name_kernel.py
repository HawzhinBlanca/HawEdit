"""Real kernel feasibility; these tests do not release the production worker."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from test_linux_bootstrap import execute


@pytest.fixture(scope="module")
def kernel_matrix(tmp_path_factory: pytest.TempPathFactory) -> list[dict[str, Any]]:
    path = Path(__file__).with_name("thread_name_kernel_probe.py")
    spec = importlib.util.spec_from_file_location("thread_name_kernel_calibration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert isinstance(module.KERNEL_CODE, str)
    compile(module.KERNEL_CODE, str(path), "exec")
    result = execute(tmp_path_factory.mktemp("thread-name-kernel"), module.KERNEL_CODE)
    status = getattr(result, "exit_code", getattr(result, "returncode", None))
    assert status == 0, result.stderr.decode("utf-8", "replace")
    record = json.loads(result.stdout)
    assert record["kind"] == "seccomp-addfd-send-userns-boundary-matrix"
    assert isinstance(record["kernel"], str) and record["kernel"]
    rows: list[dict[str, Any]] = record["results"]
    assert len(rows) == 15
    for row in rows:
        assert "probe_error" not in row, row
        assert row["exit"] == (-9 if row["mode"] == "stale" else 0), row
        if row.get("private_root"):
            assert row["coordinator_exit"] == 0 and row["root_cleanup"] is True, row
            assert row["readonly_root"] is True and row["readonly_proc"] is True, row
            assert all(int(value, 16) == 0 for value in row["controller_caps"].values())
            assert all(int(value, 16) == 0 for value in row["metadata"]["caps"].values())
            assert row["metadata"]["landlock_abi"] >= 6
    return rows


@pytest.mark.parametrize("index", range(4))
def test_thread_name_kernel_namespace_capabilities_and_landlock(
    kernel_matrix: list[dict[str, Any]], index: int
) -> None:
    row = kernel_matrix[index]
    assert row["request_admitted"] is True
    assert row["notification_pid"] == row["metadata"]["tid"]
    assert row["requested"] == f"/proc/self/task/{row['notification_pid']}/comm"
    assert row["addfd_errno"] is None and row["addfd_return"] >= 0
    assert row["worker_result"]["write"] == 10 and row["measured_comm"] == "HawUserns"
    assert row["measured_comm"] != row["before_comm"]
    if index:
        assert row["userns"] is True
    if index >= 2:
        assert all(int(value, 16) == 0 for value in row["metadata"]["caps"].values())
    if index == 3:
        assert row["metadata"]["landlock_abi"] >= 6


@pytest.mark.parametrize("private_pid", [False, True])
def test_thread_name_kernel_private_root_changes_real_comm(
    kernel_matrix: list[dict[str, Any]], private_pid: bool
) -> None:
    row = next(
        row
        for row in kernel_matrix
        if row.get("private_root") and row["private_pid"] == private_pid and row["mode"] == "valid"
    )
    assert row["request_admitted"] is True
    assert row["addfd_errno"] is None
    assert row["worker_result"]["write"] == 10
    assert row["worker_result"]["tid"] == row["notification_pid"]
    assert row["measured_comm"] == "HawUserns" and row["measured_comm"] != row["before_comm"]
    if private_pid:
        assert row["controller_pid"] == 1 and row["worker"] == 2
        assert row["notification_pid"] == 3


@pytest.mark.parametrize(
    "mode", ["foreign", "extra_flags", "bad_dirfd", "bad_path", "unterminated"]
)
def test_thread_name_kernel_refuses_unapproved_requests(
    kernel_matrix: list[dict[str, Any]], mode: str
) -> None:
    row = next(row for row in kernel_matrix if row["mode"] == mode)
    assert row["request_admitted"] is False and row["descriptor_injected"] is False
    assert row["worker_result"]["refused_errno"] == 1
    assert "write" not in row["worker_result"] and "addfd_return" not in row
    assert row["measured_comm"] == row["before_comm"]
    if mode == "unterminated":
        assert row["requested"] is None and row["bounded_copy_refusal"] == "unterminated path"


def test_thread_name_kernel_mutable_path_uses_copied_request(
    kernel_matrix: list[dict[str, Any]],
) -> None:
    row = next(row for row in kernel_matrix if row["mode"] == "mutable")
    assert row["requested"] == "/proc/self/task/3/comm"
    assert row["path_after_copy"] == "/proc/self/comm"
    assert row["addfd_errno"] is None and row["worker_result"]["write"] == 10
    assert row["measured_comm"] == "HawUserns"


def test_thread_name_kernel_stale_notification_refuses_after_original_drain(
    kernel_matrix: list[dict[str, Any]],
) -> None:
    row = next(row for row in kernel_matrix if row["mode"] == "stale")
    assert row["id_valid_errno"] == 2 and row["addfd_send_errno"] == 2
    assert row["scope_drained"] is True and row["exit"] == -9
    assert "worker_result" not in row and "addfd_return" not in row


def test_thread_name_kernel_listener_loss_refuses_real_open(
    kernel_matrix: list[dict[str, Any]],
) -> None:
    row = next(row for row in kernel_matrix if row["mode"] == "listener_loss")
    assert row["descriptor_injected"] is False and row["worker_result"]["refused_errno"] == 38
    assert row["measured_comm"] == row["before_comm"]
    assert "write" not in row["worker_result"] and "addfd_return" not in row


def test_thread_name_kernel_vendor_main_names_its_other_live_thread(
    kernel_matrix: list[dict[str, Any]],
) -> None:
    row = next(row for row in kernel_matrix if row["mode"] == "vendor_shape")
    assert row["controller_pid"] == 1 and row["worker"] == 2
    assert row["caller_tid"] == 2 and row["target_tid"] == 3
    assert row["notification_pid"] == row["caller_tid"]
    assert row["requested"] == "/proc/self/task/3/comm" and row["creation_mode"] == "0o666"
    assert row["addfd_errno"] is None and row["worker_result"]["write"] == 12
    assert row["worker_result"]["caller_tid"] == 2 and row["worker_result"]["target_tid"] == 3
    assert row["measured_comm"] == "VendorShape"
    assert row["measured_caller_comm"] == row["caller_comm_before"]
