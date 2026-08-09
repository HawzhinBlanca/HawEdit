"""M0.1 — the gate must fail loudly rather than print green while running nothing.

The gate is the only thing that may declare a task DONE, so its failure modes are worth
more than its success mode. If `verify.sh` could be neutered by pointing a step at `true`,
every DONE mark downstream of it would be worthless.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from hawedit.gate import (
    GATE_TOOLS,
    ForeignTool,
    assert_tools_are_from_this_environment,
)

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "verify.sh"

FULL_GATE_SUCCESS_LINE = "VERIFY OK"


def _bash_candidates() -> tuple[Path, ...]:
    """Return plausible Bash installations without trusting Windows command lookup.

    ``C:\\Windows\\System32`` precedes ``PATH`` for a Windows process.  Consequently
    ``shutil.which("bash")`` commonly returns WSL's launcher even when Git Bash is installed.
    Find Git Bash from the Git installation first, while retaining WSL as a usable fallback.
    """
    candidates: list[Path] = []
    configured = os.environ.get("HAWEDIT_BASH")
    if configured:
        candidates.append(Path(configured))

    git = shutil.which("git")
    if git:
        # Git for Windows installs cmd/git.exe and bin/bash.exe under the same root.
        candidates.append(Path(git).resolve().parent.parent / "bin" / "bash.exe")

    if program_files := os.environ.get("PROGRAMFILES"):
        candidates.append(Path(program_files) / "Git" / "bin" / "bash.exe")
    if local_app_data := os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(local_app_data) / "Programs" / "Git" / "bin" / "bash.exe")

    if on_path := shutil.which("bash"):
        candidates.append(Path(on_path))

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        identity = os.path.normcase(os.path.abspath(candidate))
        if identity not in seen:
            seen.add(identity)
            unique.append(candidate)
    return tuple(unique)


def _gate_paths_for_bash() -> tuple[str, ...]:
    """Spell the checkout path for native Windows Bash and for WSL."""
    paths = [GATE.as_posix()]
    if GATE.drive:
        relative = GATE.as_posix()[3:]
        paths.append(f"/mnt/{GATE.drive[0].lower()}/{relative}")
    return tuple(paths)


def _select_bash() -> tuple[str | None, str | None, str]:
    """Select a Bash that proves it can read this checkout's real gate script."""
    failures: list[str] = []
    for candidate in _bash_candidates():
        if not candidate.is_file():
            failures.append(f"{candidate}: not a file")
            continue
        for gate_path in _gate_paths_for_bash():
            try:
                probe = subprocess.run(
                    [
                        str(candidate),
                        "--noprofile",
                        "--norc",
                        "-c",
                        'test -r "$1"',
                        "hawedit-gate-probe",
                        gate_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            except OSError as exc:
                failures.append(f"{candidate}: {exc}")
                break
            except subprocess.TimeoutExpired:
                failures.append(f"{candidate}: probe timed out")
                break
            if probe.returncode == 0:
                return str(candidate), gate_path, ""
        else:
            failures.append(f"{candidate}: cannot read {GATE}")
    return None, None, "; ".join(failures) or "no Bash candidates were found"


BASH, GATE_ARGUMENT, BASH_FAILURE = _select_bash()


def _run_gate(*args: str, **env_overrides: str) -> subprocess.CompletedProcess[str]:
    """Run the real gate script, the way a developer or CI runs it.

    Two Windows-only traps, both of which turn every refusal assertion below into a false
    pass — the tests that exist to prove the gate cannot be neutered, neutered by the harness.

    `BASH`, not `"bash"`: Windows commonly resolves WSL's launcher even when Git Bash is
    installed. The resolver finds Git Bash beside `git.exe`, considers WSL as a fallback, and
    probes that the interpreter can read the real checkout before any assertion trusts it.

    `GATE_ARGUMENT`, not `str(GATE)`: native Bash needs a forward-slash Windows path while WSL
    needs `/mnt/<drive>/...`. The successful readability probe selects the matching spelling.

    `PY` defaults to the interpreter running this test. That interpreter has already passed
    the outer gate's environment preflight; letting the subprocess rediscover ``.venv`` would
    couple these contract tests to an unrelated or stale checkout-level environment. Explicit
    ``PY`` overrides remain authoritative for the refusal tests below. This is not a bypass:
    the gate itself rejects that default unless pytest is running from the canonical ``.venv``.
    """
    assert BASH is not None and GATE_ARGUMENT is not None, (
        "no Bash interpreter can access the checkout; install Git for Windows or set "
        f"HAWEDIT_BASH. Probes: {BASH_FAILURE}"
    )
    env = {**os.environ, "PY": Path(sys.executable).as_posix(), **env_overrides}
    return subprocess.run(
        [BASH, GATE_ARGUMENT, *args],
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
    assert result.returncode == 5, f"expected refusal exit 5, got {result.returncode}"
    assert "REFUSED" in result.stderr
    assert FULL_GATE_SUCCESS_LINE not in result.stdout


def test_gate_refuses_an_empty_lint_command() -> None:
    """An explicitly empty command means "run nothing" and must not fall back to a default.

    This is why the gate uses `${VAR-default}` and not `${VAR:-default}`: the colon form
    substitutes the default for an empty value, so `LINT_CMD=` would silently run the real
    linter and the gate would look configured while the operator asked for nothing.
    """
    result = _run_gate(LINT_CMD="")
    assert result.returncode == 5, f"expected refusal exit 5, got {result.returncode}"
    assert "REFUSED" in result.stderr
    assert FULL_GATE_SUCCESS_LINE not in result.stdout


def test_gate_refuses_a_whitespace_only_command() -> None:
    result = _run_gate(FORMAT_CMD="   ")
    assert result.returncode == 5
    assert "REFUSED" in result.stderr


def test_gate_refuses_a_colon_noop() -> None:
    """`:` is a shell no-op that is not spelled `true` — the refusal must catch it too."""
    result = _run_gate(TYPECHECK_CMD=":")
    assert result.returncode == 5
    assert "REFUSED" in result.stderr


def test_nested_full_gate_refuses_instead_of_recursing() -> None:
    """gate -> pytest -> gate -> pytest is a fork bomb. The nested run must stop at the tests.

    This suite runs *inside* the gate, so every call in this file is already nested. A nested
    full run must refuse (exit 4) rather than spawn another pytest.
    """
    result = _run_gate(HAWEDIT_GATE_DEPTH="1")
    assert result.returncode == 4, f"expected nested refusal exit 4, got {result.returncode}"
    assert "nested gate invocation" in result.stderr
    assert FULL_GATE_SUCCESS_LINE not in result.stdout


def test_nested_fast_run_is_still_allowed() -> None:
    """The guard must block only the test step — lint/typecheck nested are harmless."""
    result = _run_gate("--fast", HAWEDIT_GATE_DEPTH="1")
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
    assert result.returncode == 3
    assert "canonical .venv interpreter" in result.stderr


# --- audit #5: the gate was not authoritative -------------------------------------------


def test_a_step_command_that_merely_prints_cannot_produce_a_green_gate() -> None:
    """`TEST_CMD="echo skipped"` ran nothing and printed VERIFY OK (audit finding #5).

    The old defence was a blacklist of five no-op spellings — `true`, `:`, `/bin/true` and
    friends. A blacklist of ways to do nothing can never be complete: `echo`, `cat /dev/null`,
    `pytest -k nothing_matches` and `[ 1 ]` all run successfully and test nothing. The rule
    is now the other way round: the gate's steps are not configurable, and a run with any
    step replaced cannot print the success line no matter what the replacement does.
    """
    result = _run_gate(HAWEDIT_GATE_DEPTH="0", TEST_CMD="echo skipped")
    assert FULL_GATE_SUCCESS_LINE not in result.stdout, (
        "a run with a replaced test step must never print the full-gate success line"
    )
    assert result.returncode == 5, f"expected override refusal exit 5, got {result.returncode}"
    assert "TEST_CMD" in result.stderr


def test_overriding_any_step_is_refused_before_anything_runs() -> None:
    """The refusal must precede the steps: a replaced gate should cost nothing to reject."""
    for var in ("LINT_CMD", "TYPECHECK_CMD", "FORMAT_CMD", "TEST_CMD"):
        result = _run_gate(HAWEDIT_GATE_DEPTH="0", **{var: "echo pretending"})
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


def test_ci_runs_the_hawedit_gate() -> None:
    """DONE means verify.sh green AND required CI checks green. CI never ran this gate.

    The repository's CI workflow builds the host Node project and runs *its* verify.sh. No
    job installed Python, no job ran hawedit's gate — so every DONE mark in PROGRESS.md
    rested on a local run alone, on the one machine with no independent check (finding #5).
    """
    workflows = ROOT / ".github" / "workflows"
    assert workflows.is_dir(), f"no workflows directory at {workflows}"
    bodies = {p.name: p.read_text(encoding="utf-8") for p in workflows.glob("*.yml")}
    runners = [name for name, body in bodies.items() if "scripts/verify.sh" in body]
    assert runners, (
        "no CI workflow runs scripts/verify.sh — the gate exists only on Hawa's "
        f"laptop. Workflows present: {sorted(bodies)}"
    )


def _noop_interpreter(tmp_path: Path) -> str:
    """An executable that exits 0 and says nothing — the shape of every no-op interpreter."""
    fake = tmp_path / "not-python"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    return fake.as_posix()


def _token_forging_interpreter(tmp_path: Path) -> tuple[str, Path]:
    """An executable that can forge the old probe and every later command's success."""
    executed = tmp_path / "forger-executed"
    fake = tmp_path / "forging-python"
    fake.write_text(
        f"#!/bin/sh\ntouch '{executed.as_posix()}'\nprintf '%s\\n' "
        "'hawedit-environment-ok'\nexit 0\n",
        encoding="utf-8",
        newline="\n",
    )
    fake.chmod(0o755)
    return fake.as_posix(), executed


def test_probe_token_forging_executable_is_refused_before_execution(tmp_path: Path) -> None:
    fake, executed = _token_forging_interpreter(tmp_path)
    result = _run_gate(PY=fake)
    assert result.returncode == 3
    assert "canonical .venv interpreter" in result.stderr
    assert not executed.exists(), "the untrusted executable ran before its path was refused"
    assert FULL_GATE_SUCCESS_LINE not in result.stdout


def test_an_interpreter_that_cannot_run_the_project_cannot_grade_it(tmp_path: Path) -> None:
    """`PY` replaced every step at once, so the override refusal was a whitelist with a hole.

    Measured: `PY=/usr/bin/true.exe bash scripts/verify.sh` printed VERIFY OK in one second,
    exit 0, with no report written. Five steps ran `true.exe` — and the fifth is the evidence
    step that exists precisely so the exit code stops being the evidence. It was grading the
    other four, using the one skill `true.exe` has.

    LINT_CMD and friends are refused because a replaced step "proves nothing about this
    project". `PY` replaces all four and the evidence check as well, so it gets the same rule,
    stated as a capability rather than a spelling: an interpreter that cannot import `hawedit`
    is not running this project, whatever it exits. D-104.
    """
    result = _run_gate(PY=_noop_interpreter(tmp_path))
    assert FULL_GATE_SUCCESS_LINE not in result.stdout, (
        "a no-op interpreter printed the full-gate success line — the gate graded itself with "
        "something that cannot run the code"
    )
    assert result.returncode == 3, f"expected interpreter refusal exit 3, got {result.returncode}"
    assert "canonical .venv interpreter" in result.stderr
    assert "==>" not in result.stdout, "steps ran before the interpreter was checked"


def test_a_no_op_interpreter_is_refused_in_fast_mode_too(tmp_path: Path) -> None:
    """`--fast` prints its own success line, so it needs the same interpreter to be real."""
    result = _run_gate("--fast", PY=_noop_interpreter(tmp_path))
    assert result.returncode == 3
    assert "fast checks OK" not in result.stdout


def test_an_external_real_python_is_not_canonical_gate_evidence(tmp_path: Path) -> None:
    """Capability is secondary: even a real CPython outside ``.venv`` cannot grade the gate."""
    wrapper = tmp_path / "python-without-the-project"
    wrapper.write_text(
        f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" -I -S "$@"\n',
        encoding="utf-8",
        newline="\n",
    )
    wrapper.chmod(0o755)
    result = _run_gate(PY=wrapper.as_posix())
    assert result.returncode == 3, f"expected exit 3, got {result.returncode}: {result.stderr}"
    assert "canonical .venv interpreter" in result.stderr
    assert FULL_GATE_SUCCESS_LINE not in result.stdout


def test_the_projects_own_interpreter_still_passes_the_probe() -> None:
    """The control. A probe that refuses everything satisfies all three tests above and turns
    the gate into a machine that can never be green — the exact failure the override refusal
    warns about from the other side.
    """
    result = _run_gate("--fast", PY=Path(sys.executable).as_posix())
    assert result.returncode == 0, f"the real interpreter was refused: {result.stderr}"
    assert "fast checks OK" in result.stdout


# --- D-093: a real interpreter is not enough if the step's program was substituted ----------


def _forged_pytest(root: Path) -> Path:
    """A `pytest` that writes a clean JUnit report and runs nothing. Reproduction, not a tool.

    Thirty lines is the whole cost of the forgery, which is the point: this is not an exotic
    attack, it is a file in a directory named by an environment variable.
    """
    package = root / "pytest"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text('__version__ = "8.0.0"\n', encoding="utf-8")
    (package / "__main__.py").write_text(
        "import sys\n"
        "for arg in sys.argv[1:]:\n"
        "    if arg.startswith('--junitxml='):\n"
        "        cases = ''.join(\n"
        '            f\'<testcase classname="tests.t" name="t{i}" time="0.001"/>\'\n'
        "            for i in range(1200)\n"
        "        )\n"
        "        with open(arg.split('=', 1)[1], 'w', encoding='utf-8') as handle:\n"
        "            handle.write(\n"
        '                \'<testsuites><testsuite name="pytest" errors="0" failures="0" \'\n'
        '                \'skipped="0" tests="1200" time="61.5">\' + cases +\n'
        "                '</testsuite></testsuites>'\n"
        "            )\n"
        "        print('1200 passed in 61.50s')\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    return root


def test_a_forged_test_report_cannot_produce_a_green_gate(tmp_path: Path) -> None:
    """The measured defect. D-092 made `PY` real; the step's *program* was still substitutable.

    Measured before the fix: `VERIFY OK`, exit 0, four seconds, zero test bodies executed —
    layer 3 read the forged report back and accepted it, because the report was fresh, complete
    and internally consistent. Freshness could not see it: the forgery was written during this
    run, by design.

    The assertion that matters is on the **artifact the forgery corrupted**: the committed floor
    ratcheted 1,155 -> 1,200, so every honest run afterwards would have been refused for a bar
    a forgery invented. A gate that can be poisoned into permanent red by a fake green is worse
    than one that is merely fooled once.
    """
    floor_file = ROOT / "scripts" / "test-count.floor"
    floor_before = floor_file.read_bytes()

    result = _run_gate(PYTHONPATH=str(_forged_pytest(tmp_path)))

    assert FULL_GATE_SUCCESS_LINE not in result.stdout, (
        "a forged JUnit report produced the full-gate success line"
    )
    assert result.returncode == 3, f"expected exit 3, got {result.returncode}: {result.stderr}"
    assert "pytest ->" in result.stderr, (
        f"the refusal did not name the substituted tool: {result.stderr}"
    )
    assert floor_file.read_bytes() == floor_before, (
        "the run moved scripts/test-count.floor — a refused gate must not touch the ratchet"
    )


def test_a_tool_with_no_file_is_refused_rather_than_crashing(tmp_path: Path) -> None:
    """A namespace package imports with `__file__ = None`, which `Path(None)` cannot resolve.

    Unit-level on purpose. Routing this through `PYTHONPATH` does not reproduce it: a namespace
    portion loses to a regular package found later on the path, so the real `pytest` still won
    and the gate ran on to the format step. That version of this test asserted a refusal that
    was never going to happen — the mechanism, not the guard, was wrong.

    The branch stays because the case is reachable when the tool is *not* installed and a bare
    directory of that name is on the path: the difference between a caught forgery and a gate
    that looks broken.
    """
    (tmp_path / "hawedit_tool_with_no_file").mkdir()
    sys.path.insert(0, str(tmp_path))
    try:
        with pytest.raises(ForeignTool, match="namespace package with no file"):
            assert_tools_are_from_this_environment(("hawedit_tool_with_no_file",))
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("hawedit_tool_with_no_file", None)


def test_a_tool_outside_the_environment_is_named_not_merely_counted(tmp_path: Path) -> None:
    """The refusal has to say which tool and where from, or exit 3 is a riddle."""
    package = tmp_path / "hawedit_tool_from_elsewhere"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        with pytest.raises(ForeignTool) as caught:
            assert_tools_are_from_this_environment(("hawedit_tool_from_elsewhere",))
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("hawedit_tool_from_elsewhere", None)
    assert "hawedit_tool_from_elsewhere ->" in str(caught.value)
    assert str(tmp_path.resolve()) in str(caught.value)


def test_a_missing_tool_is_refused_and_says_which() -> None:
    with pytest.raises(ForeignTool, match="hawedit_tool_that_is_not_installed does not import"):
        assert_tools_are_from_this_environment(("hawedit_tool_that_is_not_installed",))


def test_this_environments_tools_are_accepted() -> None:
    """The control. A provenance rule that refuses everything satisfies both tests above and
    makes the gate unrunnable — and `pytest` running this line is the proof it is wrong.
    """
    assert_tools_are_from_this_environment()  # must not raise in the environment CI installs


def test_every_gate_step_program_is_covered_by_the_provenance_rule() -> None:
    """A tool the gate runs but does not check is a hole the shape of the one just closed."""
    steps = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
    for tool in GATE_TOOLS:
        assert f"-m {tool}" in steps, f"{tool} is checked but is not a gate step"
    for invoked in re.findall(r"\$PY -m ([a-z_]+)", steps):
        if invoked.startswith("hawedit"):
            continue  # editable install: its file lives in the checkout by design
        assert invoked in GATE_TOOLS, (
            f"verify.sh runs `-m {invoked}` but GATE_TOOLS does not check where it came from"
        )
