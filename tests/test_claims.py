"""What the documentation claims must be true of the code — audit findings #1 and #10.

Two of the ten audit findings were not code defects at all. `README.md` opened with
"Implements BLUEPRINT.md v1.1", which a reader takes as *the system is built*; and two ledger
rows were marked DONE whose stated Definition of Done was not met — §4.1 normalization with
one of five collisions unimplemented, and a "diarization benchmark" that was the metric with
no benchmark behind it.

Prose drifts from code silently, which is exactly why it needs tests rather than care. The
checks here are deliberately narrow: each one pins a specific claim to a specific fact that a
future change would flip. When conjunctive `و` separation lands, the test that keeps M0.3 out
of DONE fails and tells you to promote it — the ledger cannot be right and the test red at
the same time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hawedit2.normalize import normalize_sorani

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
PROGRESS = (ROOT / "PROGRESS.md").read_text(encoding="utf-8")


def _ledger_row(task: str) -> str:
    """The PROGRESS.md row for one task id, e.g. "M0.3"."""
    for line in PROGRESS.splitlines():
        if line.startswith(f"| {task} |"):
            return line
    raise AssertionError(f"no ledger row for {task} in PROGRESS.md")


def _status(task: str) -> str:
    cells = [c.strip() for c in _ledger_row(task).split("|")]
    return cells[3]


# --- #10 a DONE mark must be backed by the thing it claims -------------------------------


def test_normalization_is_not_marked_done_while_a_collision_is_unhandled() -> None:
    """§4.1 lists five collisions. KLPT covers four (D-003).

    When conjunctive `و` separation is implemented this test fails — that is its job. Promote
    M0.3 to DONE in the same commit, and delete this test in favour of the one in
    tests/test_normalize.py that will then be asserting the behaviour rather than the gap.
    """
    joined_waw_is_unhandled = normalize_sorani("من وتو") == "من وتو"
    if joined_waw_is_unhandled:
        assert _status("M0.3") != "DONE", (
            "M0.3 claims §4.1 normalization is done, but conjunctive `و` separation — one of "
            "the five collisions §4.1 lists — leaves input unchanged. Mark it PARTIAL and name "
            "the shortfall, or implement it (M1.7)."
        )
    else:
        pytest.fail(
            "conjunctive `و` separation now changes output. Implement M1.7 properly, promote "
            "M0.3 to DONE, and remove this guard."
        )


def test_the_diarization_benchmark_is_not_marked_done_without_a_benchmark() -> None:
    """M0.10's Definition of Done says "DER on Kurdish multi-speaker material".

    Metric code is not a benchmark result. The evidence for a run is a file recording the
    numbers; until one exists the row cannot be DONE.
    """
    evidence = ROOT / "evidence" / "diarization-benchmark.md"
    if not evidence.exists():
        assert _status("M0.10") != "DONE", (
            "M0.10 claims a diarization benchmark on Kurdish multi-speaker material, but no "
            f"result is recorded at {evidence.relative_to(ROOT)}. The metric being implemented "
            "and the benchmark having been run are different facts."
        )


def test_every_ledger_row_marked_partial_names_its_shortfall() -> None:
    """PARTIAL without a named shortfall is DONE with extra steps."""
    for line in PROGRESS.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) > 4 and cells[3] == "PARTIAL":
            assert "Shortfall" in cells[4], f"PARTIAL row names no shortfall:\n{line}"


def test_every_blocked_row_points_at_a_blocked_entry() -> None:
    blocked = (ROOT / "BLOCKED.md").read_text(encoding="utf-8")
    open_entries = set(re.findall(r"^##\s*#(\d+)", blocked, re.MULTILINE))
    for line in PROGRESS.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) > 4 and cells[3] == "BLOCKED":
            cited = set(re.findall(r"`BLOCKED\.md`\s*#(\d+)", cells[4]))
            assert cited, f"BLOCKED row cites no entry:\n{line}"
            assert cited <= open_entries, (
                f"{cells[1]} cites BLOCKED.md #{sorted(cited - open_entries)}, which does not "
                f"exist. Entries present: {sorted(open_entries)}"
            )


# --- #1 the README must not describe a product that does not exist -----------------------


def test_the_readme_says_plainly_that_there_is_no_end_to_end_product() -> None:
    """The old opening line read as a completion claim to anyone who did not read on."""
    assert "There is no end-to-end product yet" in README, (
        "README must state the absence of a runnable pipeline in its own words, near the top — "
        "not leave it to be inferred from a milestone table."
    )
    opening = README.lstrip().split("\n\n", 2)[1]
    assert not opening.startswith("Implements"), (
        f"the README opens by claiming the blueprint is implemented: {opening!r}"
    )


def test_every_stage_the_readme_calls_not_written_really_has_no_module() -> None:
    """The status table must not go stale in the optimistic direction.

    Stage 3 and Stage 4 are listed as not written. If someone builds one and forgets the
    README, this fails — understating what exists is a smaller sin than overstating it, but
    the table is only trustworthy if it tracks in both directions.
    """
    not_written = {
        "3": ROOT / "src" / "hawedit2" / "discovery.py",
        "4": ROOT / "src" / "hawedit2" / "judge.py",
    }
    for stage, module in not_written.items():
        row = next(line for line in README.splitlines() if line.startswith(f"| {stage} ·"))
        claims_absent = "not written" in row
        assert claims_absent == (not module.exists()), (
            f"README says Stage {stage} is {'not written' if claims_absent else 'written'}, "
            f"but {module.name} {'exists' if module.exists() else 'does not exist'}"
        )


def test_every_shell_command_the_readme_offers_exists() -> None:
    """A README that tells you to run a script that was renamed is a broken promise."""
    for script in set(re.findall(r"bash (scripts/[\w.-]+\.sh)", README)):
        assert (ROOT / script).exists(), f"README offers `bash {script}`, which does not exist"


def test_every_module_invocation_the_readme_offers_is_importable() -> None:
    from importlib.util import find_spec

    for module in set(re.findall(r"python -m (hawedit2[\w.]*)", README)):
        assert find_spec(module) is not None, f"README offers `python -m {module}`, which is not"


def test_every_module_the_readme_maps_exists() -> None:
    """The module map is the README's most load-bearing table; a stale row misdirects."""
    for name in set(re.findall(r"^\| `(\w+\.py)` \|", README, re.MULTILINE)):
        assert (ROOT / "src" / "hawedit2" / name).exists(), f"module map lists missing {name}"


def test_the_module_map_covers_every_module() -> None:
    mapped = set(re.findall(r"^\| `(\w+\.py)` \|", README, re.MULTILINE))
    on_disk = {p.name for p in (ROOT / "src" / "hawedit2").glob("*.py")} - {"__init__.py"}
    assert on_disk <= mapped, f"modules absent from the README map: {sorted(on_disk - mapped)}"
