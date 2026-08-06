"""M0.1 — the gate must fail loudly rather than print green while running nothing.

The gate is the only thing that may declare a task DONE, so its failure modes are worth
more than its success mode. If `verify.sh` could be neutered by pointing a step at `true`,
every DONE mark downstream of it would be worthless.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "verify.sh"

FULL_GATE_SUCCESS_LINE = "VERIFY OK"


def _run_gate(*args: str, **env_overrides: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **env_overrides}
    return subprocess.run(
        ["bash", str(GATE), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
        check=False,
    )


def test_gate_is_executable() -> None:
    assert GATE.exists(), "the gate script must exist"
    assert os.access(GATE, os.X_OK), "the gate script must be executable"


def test_gate_refuses_a_noop_test_command() -> None:
    """`TEST_CMD=true` is the canonical cheat: the gate would run nothing and print green."""
    result = _run_gate(TEST_CMD="true")
    assert result.returncode == 3, f"expected refusal exit 3, got {result.returncode}"
    assert "REFUSED" in result.stderr
    assert FULL_GATE_SUCCESS_LINE not in result.stdout


def test_gate_refuses_an_empty_lint_command() -> None:
    """An explicitly empty command means "run nothing" and must not fall back to a default.

    This is why the gate uses `${VAR-default}` and not `${VAR:-default}`: the colon form
    substitutes the default for an empty value, so `LINT_CMD=` would silently run the real
    linter and the gate would look configured while the operator asked for nothing.
    """
    result = _run_gate(LINT_CMD="")
    assert result.returncode == 3, f"expected refusal exit 3, got {result.returncode}"
    assert "REFUSED" in result.stderr
    assert FULL_GATE_SUCCESS_LINE not in result.stdout


def test_gate_refuses_a_whitespace_only_command() -> None:
    result = _run_gate(FORMAT_CMD="   ")
    assert result.returncode == 3
    assert "REFUSED" in result.stderr


def test_gate_refuses_a_colon_noop() -> None:
    """`:` is a shell no-op that is not spelled `true` — the refusal must catch it too."""
    result = _run_gate(TYPECHECK_CMD=":")
    assert result.returncode == 3
    assert "REFUSED" in result.stderr


def test_nested_full_gate_refuses_instead_of_recursing() -> None:
    """gate -> pytest -> gate -> pytest is a fork bomb. The nested run must stop at the tests.

    This suite runs *inside* the gate, so every call in this file is already nested. A nested
    full run must refuse (exit 4) rather than spawn another pytest.
    """
    result = _run_gate(HAWEDIT2_GATE_DEPTH="1")
    assert result.returncode == 4, f"expected nested refusal exit 4, got {result.returncode}"
    assert "nested gate invocation" in result.stderr
    assert FULL_GATE_SUCCESS_LINE not in result.stdout


def test_nested_fast_run_is_still_allowed() -> None:
    """The guard must block only the test step — lint/typecheck nested are harmless."""
    result = _run_gate("--fast", HAWEDIT2_GATE_DEPTH="1")
    assert result.returncode == 0, result.stderr
    assert FULL_GATE_SUCCESS_LINE not in result.stdout


def test_fast_mode_never_claims_the_full_gate_passed() -> None:
    """A --fast run skips tests; it must not emit a line a human could read as a green gate."""
    result = _run_gate("--fast")
    assert FULL_GATE_SUCCESS_LINE not in result.stdout, (
        "--fast must not print the full-gate success line — it did not run the tests"
    )


def test_gate_fails_when_the_interpreter_is_missing() -> None:
    result = _run_gate(PY="/nonexistent/python")
    assert result.returncode == 2
    assert "no interpreter" in result.stderr
