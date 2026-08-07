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


# --- audit #5: the gate was not authoritative -------------------------------------------


def test_a_step_command_that_merely_prints_cannot_produce_a_green_gate() -> None:
    """`TEST_CMD="echo skipped"` ran nothing and printed VERIFY OK (audit finding #5).

    The old defence was a blacklist of five no-op spellings — `true`, `:`, `/bin/true` and
    friends. A blacklist of ways to do nothing can never be complete: `echo`, `cat /dev/null`,
    `pytest -k nothing_matches` and `[ 1 ]` all run successfully and test nothing. The rule
    is now the other way round: the gate's steps are not configurable, and a run with any
    step replaced cannot print the success line no matter what the replacement does.
    """
    result = _run_gate(HAWEDIT2_GATE_DEPTH="0", TEST_CMD="echo skipped")
    assert FULL_GATE_SUCCESS_LINE not in result.stdout, (
        "a run with a replaced test step must never print the full-gate success line"
    )
    assert result.returncode == 5, f"expected override refusal exit 5, got {result.returncode}"
    assert "TEST_CMD" in result.stderr


def test_overriding_any_step_is_refused_before_anything_runs() -> None:
    """The refusal must precede the steps: a replaced gate should cost nothing to reject."""
    for var in ("LINT_CMD", "TYPECHECK_CMD", "FORMAT_CMD", "TEST_CMD"):
        result = _run_gate(HAWEDIT2_GATE_DEPTH="0", **{var: "echo pretending"})
        assert result.returncode == 5, f"{var} override was not refused"
        assert var in result.stderr
        assert "==>" not in result.stdout, f"{var}: steps ran before the override was refused"


def test_the_unmodified_gate_is_not_treated_as_an_override() -> None:
    """The refusal keys on the variable being set at all, so the normal path must stay green."""
    result = _run_gate("--fast")
    assert result.returncode == 0, result.stderr


def test_shell_scripts_are_pinned_to_lf_line_endings() -> None:
    """A CRLF checkout breaks the gate on line 1: `set -euo pipefail\\r` is not an option name.

    Hawa develops on Windows, where `core.autocrlf=true` is the installer default. Without a
    .gitattributes rule the gate is unrunnable on the machine it was written for — the audit
    reported this as the gate not being authoritative, and it is the most literal form of it:
    a gate that cannot start cannot refuse anything.
    """
    attributes = ROOT / ".gitattributes"
    assert attributes.exists(), "no .gitattributes — a Windows checkout will CRLF the gate"
    rules = attributes.read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in rules, f"shell scripts are not pinned to LF:\n{rules}"


def test_no_committed_shell_script_contains_a_carriage_return() -> None:
    for script in sorted((ROOT / "scripts").glob("*.sh")):
        assert b"\r" not in script.read_bytes(), (
            f"{script.name} contains CR bytes — bash will fail on the first `set` line"
        )


def test_ci_runs_the_hawedit2_gate() -> None:
    """DONE means verify.sh green AND required CI checks green. CI never ran this gate.

    The repository's CI workflow builds the host Node project and runs *its* verify.sh. No
    job installed Python, no job ran hawedit2's gate — so every DONE mark in PROGRESS.md
    rested on a local run alone, on the one machine with no independent check (finding #5).
    """
    workflows = ROOT.parent / ".github" / "workflows"
    assert workflows.is_dir(), f"no workflows directory at {workflows}"
    bodies = {p.name: p.read_text(encoding="utf-8") for p in workflows.glob("*.yml")}
    runners = [name for name, body in bodies.items() if "hawedit2/scripts/verify.sh" in body]
    assert runners, (
        "no CI workflow runs hawedit2/scripts/verify.sh — the gate exists only on Hawa's "
        f"laptop. Workflows present: {sorted(bodies)}"
    )
