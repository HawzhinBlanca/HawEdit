"""Actual notification/descriptor/timeout behavior, never mocked kernel results."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from test_linux_bootstrap import execute
from thread_name_broker_probe import broker_program


def observe(tmp_path: Path, case: str) -> dict[str, Any]:
    result = execute(tmp_path, broker_program(case))
    status = getattr(result, "exit_code", getattr(result, "returncode", None))
    assert status == 0, result.stderr.decode("utf-8", "replace")
    record: dict[str, Any] = json.loads(result.stdout)
    assert "error" not in record, record
    assert record["coordinator_exit"] == 0 and record["root_cleanup"], record
    assert record["readonly_root"] and record["readonly_proc"]
    assert record["drained"] and record["observed"] == record["reaped"] == [2, 3]
    return record


def test_thread_broker_actual_fopen_and_atomic_injection(tmp_path: Path) -> None:
    row = observe(tmp_path, "positive")
    assert row["broker_result"]["accepted"]
    assert row["broker_result"]["descriptor"] >= 0
    assert row["broker_result"]["caller_tid"] == 2
    assert row["broker_result"]["target_tid"] == 3
    assert row["write_result"] == {"written": 11}
    assert row["measured_comm"] == "Registered"
    assert row["worker_exit"] == 0


def test_thread_broker_foreign_target_refuses(tmp_path: Path) -> None:
    row = observe(tmp_path, "foreign")
    assert not row["broker_result"]["accepted"]
    assert row["broker_result"]["descriptor"] is None
    assert row["broker_result"]["error"] == 1
    assert row["write_result"]["errno"] == 1
    assert "genuine libc fopen" in row["write_result"]["worker_error"]
    assert row["worker_exit"] == 71


def test_thread_broker_idle_receive_has_real_deadline(tmp_path: Path) -> None:
    row = observe(tmp_path, "idle")
    assert "deadline" in row["broker_refusal"]
    assert 0.09 <= row["idle_elapsed_s"] < 1.0
    assert row["handler_restored"] and row["timer_restored"]
    assert row["worker_exit"] == -9


def test_thread_broker_listener_substitution_preserves_foreign_slot(tmp_path: Path) -> None:
    row = observe(tmp_path, "substitution")
    assert "description" in row["broker_refusal"]
    assert "description" in row["broker_cleanup_refusal"]
    assert row["foreign_preserved"]
    assert row["worker_exit"] == -9


def test_thread_broker_non_listener_refuses(tmp_path: Path) -> None:
    row = observe(tmp_path, "bad_listener")
    assert "listener" in row["broker_refusal"]
    assert row["worker_exit"] == -9


@pytest.mark.parametrize("value", [True, None, "5", 0, -1, float("nan"), float("inf"), 31])
def test_thread_broker_invalid_deadline(value: object) -> None:
    module = importlib.import_module("hawedit.linux_thread_name")
    with pytest.raises(module.LinuxThreadNameError, match="deadline"):
        module.LinuxThreadNameBroker(None, -1, timeout_seconds=value)


@pytest.mark.parametrize("case", ["flags", "mode", "dirfd", "path"])
def test_thread_broker_exact_open_shape_refuses(tmp_path: Path, case: str) -> None:
    row = observe(tmp_path, case)
    assert not row["broker_result"]["accepted"]
    assert row["broker_result"]["descriptor"] is None
    assert row["broker_result"]["error"] == 1
    assert row["write_result"] == {"refused_errno": 1}
    assert row["worker_exit"] == 0


def test_thread_broker_preserves_original_timer_without_extending_it(tmp_path: Path) -> None:
    row = observe(tmp_path, "existing_timer")
    assert "deadline" in row["broker_refusal"]
    assert 0.09 <= row["idle_elapsed_s"] < 1.0
    assert row["handler_restored"]
    assert 0 < row["remaining_original_timer"] < 0.95
    assert row["worker_exit"] == -9


def test_thread_broker_refuses_foreign_watchdog_handler(tmp_path: Path) -> None:
    row = observe(tmp_path, "foreign_handler")
    assert "watchdog" in row["broker_refusal"]
    assert row["handler_restored"] and row["timer_restored"]
    assert row["idle_elapsed_s"] < 1.0
    assert row["worker_exit"] == -9


def test_thread_broker_respects_earlier_original_deadline(tmp_path: Path) -> None:
    row = observe(tmp_path, "earlier_timer")
    assert "deadline" in row["broker_refusal"]
    assert 0.04 <= row["idle_elapsed_s"] < 0.5
    assert row["handler_restored"] and row["timer_restored"]
    assert row["worker_exit"] == -9


def test_thread_broker_does_not_replace_periodic_timer(tmp_path: Path) -> None:
    row = observe(tmp_path, "periodic_timer")
    assert "watchdog" in row["broker_refusal"]
    assert row["handler_restored"]
    assert 0 < row["periodic_remaining"][0] <= 1.0
    assert row["periodic_remaining"][1] == 1.0
    assert row["worker_exit"] == -9
