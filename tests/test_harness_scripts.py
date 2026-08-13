"""The two CODYSTEM scripts that decide what "done" means had no automated test at all.

`scripts/update-ledger.sh` is the only thing permitted to flip a ledger row, and
`scripts/claude-stop-verify.sh` is what turns a red gate into an agent that must fix it rather
than stop. Both landed in D-198, which recorded the omission and its reason in the same breath:
"a Python test of it would have moved that floor and is left as separate work"
(`DECISIONS.md:10265-10272`). This is that work.

Both scripts locate the repository from their own location — `update-ledger.sh:25-26` and
`claude-stop-verify.sh:29-30` each `cd` to `$(dirname "$0")/..`. Copying one into a tmpdir
therefore makes that tmpdir its whole world, which is what lets these tests run against a stub
gate instead of the real one. That matters three ways: milliseconds rather than the gate's
~2m40s; nothing touches `.gate/last-test-run.xml` or `scripts/test-count.floor`, which a second
session in this shared checkout may be using at the same moment (BLOCKED #12); and the stub can
record *that it ran*, which is how "this refusal never reaches the gate" becomes an assertion
rather than a reading of the source.

What is deliberately not covered here: everything below `update-ledger.sh:78`, where the real
gate is invoked. pytest runs underneath that gate, `verify.sh:100-101` exports
`HAWEDIT_GATE_DEPTH`, and `verify.sh:117-118` refuses a nested full run with exit 4 — so the
citation check, the flip and the provenance line cannot be reached from a test in this suite at
all. They are proved by running the real script by hand against a real ledger; see
`specs/harness-integrity/spec.md`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEDGER_FLIPPER = ROOT / "scripts" / "update-ledger.sh"
STOP_HOOK = ROOT / "scripts" / "claude-stop-verify.sh"
BASH = shutil.which("bash")

needs_bash = pytest.mark.skipif(BASH is None, reason="needs bash")

# The stub gate appends to this on every invocation. Its absence is the evidence that a refusal
# fired before `update-ledger.sh:78` rather than after it.
GATE_MARKER = "gate-ran"

DEMO_LEDGER = """# Tasks ledger — demo

- [ ] T1  a task that is not done yet   (tests: test_one)
- [x] T2  a task already marked done    (tests: test_two)
- [ ] T10  a longer id that shares T1's prefix   (tests: test_ten)
"""


def sandbox(tmp_path: Path, script: Path, *, gate_exit: int = 0) -> Path:
    """A tmpdir laid out so `script` believes it is the repository root.

    The stub `verify.sh` is what keeps the real gate out of these tests. It is not a fake of the
    thing under test — D-092 and D-093 forbid that, and rightly — it stands in for a *different*
    program that the script under test only calls and never inspects.
    """
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(script, scripts / script.name)
    marker = (tmp_path / GATE_MARKER).as_posix()
    (scripts / "verify.sh").write_text(
        f'#!/usr/bin/env bash\nprintf "ran\\n" >> "{marker}"\nexit {gate_exit}\n',
        encoding="utf-8",
    )
    return tmp_path


def write_ledger(root: Path, feature: str, body: str = DEMO_LEDGER) -> Path:
    """The target `update-ledger.sh:38` computes as `specs/<feature>/tasks.md`."""
    ledger = root / "specs" / feature / "tasks.md"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(body, encoding="utf-8")
    return ledger


def gate_ran(root: Path) -> bool:
    """Whether the stub gate was invoked at all — the evidence behind every "before :78" claim."""
    return (root / GATE_MARKER).exists()


def run_ledger(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        # The resolved bash, and POSIX paths: `subprocess` finds WSL's bash.exe on Windows, which
        # cannot open a `C:/…` path at all, and bash eats the backslashes (D-120).
        [BASH, (root / "scripts" / LEDGER_FLIPPER.name).as_posix(), *args],
        capture_output=True,
        text=True,
        errors="replace",
        cwd=root,
        # An explicit copy, never a mutation of `os.environ`: D-189 records a harness that set
        # gate variables in place, leaked them into the suite's own gate-invoking tests on
        # Windows, and reported a false FAIL. `HAWEDIT_GATE_DEPTH` is passed through untouched —
        # clearing it here is precisely what would let a real nested gate start.
        env=dict(os.environ),
    )


@needs_bash
def test_the_ledger_flipper_refuses_fewer_than_three_arguments(tmp_path: Path) -> None:
    """Feature, task and citations are all required; any two of the three is not a usable call."""
    root = sandbox(tmp_path, LEDGER_FLIPPER)
    write_ledger(root, "demo")
    for args in ([], ["demo"], ["demo", "T1"]):
        result = run_ledger(root, *args)
        assert result.returncode == 2, f"{args!r}: {result.stderr}"
        assert "usage:" in result.stderr


@needs_bash
def test_the_ledger_flipper_refuses_a_task_id_outside_the_allowed_set(tmp_path: Path) -> None:
    """`$task` is interpolated straight into a `grep -E` pattern at `update-ledger.sh:67`.

    The script explains the choice at :46-48 — the argument is constrained rather than escaped,
    because "a rejected argument is a better outcome than a metacharacter quietly widening a
    match that decides what counts as done".
    """
    root = sandbox(tmp_path, LEDGER_FLIPPER)
    write_ledger(root, "demo")
    for task in ("T*", "T1|T2", "T 1", "T$", "^T1", "T1)"):
        result = run_ledger(root, "demo", task, "test_one")
        assert result.returncode == 2, f"{task!r}: {result.stderr}"
        assert "is not [A-Za-z0-9_.-]+" in result.stderr


@needs_bash
def test_the_ledger_flipper_refuses_a_citation_that_is_not_a_plain_test_name(
    tmp_path: Path,
) -> None:
    """Each citation is looked up by name in the JUnit report (`update-ledger.sh:88-97`).

    A node id, a `-k` expression or a path is not a name, and would be looked up forever without
    ever matching — so it is refused at the door with a message saying what to cite instead.
    """
    root = sandbox(tmp_path, LEDGER_FLIPPER)
    write_ledger(root, "demo")
    for cite in ("tests/test_x.py::test_one", "test_one or test_two", "-k test_one", "test one"):
        result = run_ledger(root, "demo", "T1", cite)
        assert result.returncode == 2, f"{cite!r}: {result.stderr}"
        assert "is not a plain test name" in result.stderr


ONLY_T10 = """# Tasks ledger — demo

- [ ] T10  the only row in this ledger   (tests: test_ten)
"""


@needs_bash
def test_the_ledger_flipper_refuses_a_feature_with_no_ledger(tmp_path: Path) -> None:
    """`update-ledger.sh:41-44`. Until this feature there was no `specs/<f>/tasks.md` anywhere,
    so this refusal is the one that fired on every invocation the repository ever made."""
    root = sandbox(tmp_path, LEDGER_FLIPPER)
    result = run_ledger(root, "nosuchfeature", "T1", "test_one")
    assert result.returncode == 2, result.stderr
    assert "no ledger at specs/nosuchfeature/tasks.md" in result.stderr


@needs_bash
def test_the_ledger_flipper_refuses_a_task_id_with_no_row(tmp_path: Path) -> None:
    """A citation cannot invent the row it flips."""
    root = sandbox(tmp_path, LEDGER_FLIPPER)
    write_ledger(root, "demo")
    result = run_ledger(root, "demo", "T99", "test_one")
    assert result.returncode == 2, result.stderr
    assert "no row for task 'T99'" in result.stderr


@needs_bash
def test_the_ledger_flipper_does_not_prefix_match_a_longer_task_id(tmp_path: Path) -> None:
    """Features reuse T1..T4, and a prefix match makes T1 flip T10 too (`update-ledger.sh:17-18`).

    The ledger here holds only T10. Asking for T1 must find nothing: the trailing
    `([[:space:]]|$)` in the pattern at :67 is the whole difference, and without it this call
    would sail past the row check and into the gate.
    """
    root = sandbox(tmp_path, LEDGER_FLIPPER)
    write_ledger(root, "demo", ONLY_T10)
    result = run_ledger(root, "demo", "T1", "test_one")
    assert result.returncode == 2, result.stderr
    assert "no row for task 'T1'" in result.stderr
    assert not gate_ran(root)


@needs_bash
def test_the_ledger_flipper_short_circuits_a_row_already_marked_done(tmp_path: Path) -> None:
    """Re-flipping a done row is a no-op that must not spend 2m35s of gate to discover it."""
    root = sandbox(tmp_path, LEDGER_FLIPPER)
    ledger = write_ledger(root, "demo")
    before = ledger.read_text(encoding="utf-8")
    result = run_ledger(root, "demo", "T2", "test_two")
    assert result.returncode == 0, result.stderr
    assert "Nothing to do" in result.stdout
    assert not gate_ran(root)
    assert ledger.read_text(encoding="utf-8") == before


@needs_bash
def test_no_refusal_path_reaches_the_gate(tmp_path: Path) -> None:
    """Every refusal fires above `update-ledger.sh:78`, where the real gate is invoked.

    This is the property that makes the rest of this file cheap and safe to run inside the very
    suite the gate is grading: a refusal that reached the gate would recurse into it. Asserted
    against evidence the stub writes, not against a reading of the source.
    """
    with_ledger = sandbox(tmp_path / "a", LEDGER_FLIPPER)
    write_ledger(with_ledger, "demo")
    for args in (
        (),
        ("demo",),
        ("demo", "T1"),
        ("demo", "T*", "test_one"),
        ("demo", "T1", "-k test_one"),
        ("demo", "T99", "test_one"),
        ("demo", "T2", "test_two"),
    ):
        run_ledger(with_ledger, *args)
        assert not gate_ran(with_ledger), f"{args!r} reached the gate"

    without_ledger = sandbox(tmp_path / "b", LEDGER_FLIPPER)
    run_ledger(without_ledger, "demo", "T1", "test_one")
    assert not gate_ran(without_ledger)


def run_stop_hook(root: Path, payload: str = "") -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, (root / "scripts" / STOP_HOOK.name).as_posix()],
        input=payload,
        capture_output=True,
        text=True,
        errors="replace",
        cwd=root,
        env=dict(os.environ),
    )


@needs_bash
@pytest.mark.parametrize(
    ("gate_exit", "hook_exit"),
    [(0, 0), (1, 2), (2, 1), (3, 2), (4, 1), (5, 2), (9, 2)],
)
def test_the_stop_hook_maps_every_gate_exit_code(
    tmp_path: Path, gate_exit: int, hook_exit: int
) -> None:
    """The map at `claude-stop-verify.sh:44-67` is the entire reason the wrapper exists.

    Claude Code gives exit 2 one specific meaning — block, and feed stderr back to the agent —
    while `verify.sh` already spends 2 on "no interpreter in .venv". Wired up raw the two land
    exactly backwards: a failing suite would become a notice the agent stops straight through,
    and an unprovisioned checkout would block it on a condition nobody explained. 9 stands for
    any code the map does not name, and must block: unknown is not green.
    """
    root = sandbox(tmp_path, STOP_HOOK, gate_exit=gate_exit)
    result = run_stop_hook(root)
    assert result.returncode == hook_exit, (
        f"gate {gate_exit} -> {result.returncode}: {result.stderr}"
    )
    assert gate_ran(root)


@needs_bash
def test_the_stop_hook_lets_go_when_it_is_already_active(tmp_path: Path) -> None:
    """Loop safety (`claude-stop-verify.sh:23-26`): blocking on the second pass is how a hook
    turns a red gate into an agent that can never stop at all.

    The gate here is red — exit 1, which maps to block — and the hook must still let go, and
    must not spend a gate run to decide that.
    """
    root = sandbox(tmp_path, STOP_HOOK, gate_exit=1)
    result = run_stop_hook(root, '{"stop_hook_active": true}')
    assert result.returncode == 0, result.stderr
    assert not gate_ran(root)


# --- the wiring, which decides whether any of the above is ever invoked -----------------------
#
# Everything above tests what the scripts do when they run. Nothing tested whether Claude Code is
# configured to run them at all — and a hook whose command names a path that does not exist fails
# silently by design, because a hook that cannot start must not wedge the agent. So a typo in
# `.claude/settings.json` retires the guard, or the Stop gate, and every run stays green.


SETTINGS = ROOT / ".claude" / "settings.json"


def _hook_commands() -> dict[str, list[str]]:
    """Every hook command in the settings file, keyed by event."""
    config = json.loads(SETTINGS.read_text(encoding="utf-8"))
    found: dict[str, list[str]] = {}
    for event, entries in config["hooks"].items():
        for entry in entries:
            for hook in entry["hooks"]:
                found.setdefault(event, []).append(hook["command"])
    return found


def test_every_hook_command_names_a_script_that_exists() -> None:
    """The failure this catches is silent in both directions.

    `guard-pretooluse.sh` is written to allow the call when it cannot start — a guard that
    fails closed on its own absence would wedge the agent — and Claude Code does not fail a
    session because a hook's command was not found. So a renamed or mistyped script leaves the
    boundary open with nothing on screen to say so.
    """
    commands = _hook_commands()
    assert set(commands) == {"PreToolUse", "PostToolUse", "Stop"}, sorted(commands)

    referenced = [
        (event, name)
        for event, cmds in commands.items()
        for cmd in cmds
        for name in re.findall(r"scripts/[A-Za-z0-9_.-]+\.sh", cmd)
    ]
    assert referenced, "no hook names a script at all"
    for event, name in referenced:
        assert (ROOT / name).is_file(), f"the {event} hook names {name}, which does not exist"


def test_the_guard_covers_every_tool_that_can_write() -> None:
    """The guard's file_path branch and its shell branch are both reachable only if the matcher
    selects the tools that use them. Dropping `Write` from the matcher would leave `Edit`
    guarded and `Write` open, which reads as a working guard.
    """
    matchers = json.loads(SETTINGS.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    covered = {tool for entry in matchers for tool in entry["matcher"].split("|")}
    assert {"Bash", "Edit", "Write", "MultiEdit"} <= covered, sorted(covered)


def test_the_stop_hook_runs_the_wrapper_and_never_the_gate_directly() -> None:
    """D-198's whole reason for `claude-stop-verify.sh` existing.

    Claude Code gives exit 2 one meaning — block, and feed stderr back to the agent — while
    `verify.sh` already spends 2 on "no interpreter in .venv". Wired raw the two land exactly
    backwards: a failing suite becomes a notice the agent stops straight through, and an
    unprovisioned checkout blocks it on a condition nobody explained. A later simplification of
    this line to call the gate directly would be silent, and this is what refuses it.
    """
    (command,) = _hook_commands()["Stop"]
    assert "claude-stop-verify.sh" in command
    assert "verify.sh" not in command.replace("claude-stop-verify.sh", "")
