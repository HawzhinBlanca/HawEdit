"""The gate must prove the tests ran, not assume it because the command exited 0.

Refusing to let anyone replace the test step (tests/test_gate.py) closes the deliberate
bypass. It does not close the accidental one: a `testpaths` typo, a collection error swallowed
by a plugin, a `-k` filter left in `addopts` — each makes pytest exit 0 having run nothing at
all. That failure is quieter than the one the audit found, because nobody chose it.

So the gate stops reading the exit code as evidence. It deletes the report, runs pytest under
`--junitxml`, and then demands a fresh report showing a plausible number of collected tests
and zero failures. The floor ratchets upward: deleting tests is allowed, but only as a visible
edit to a committed number, never as a silent drop in coverage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.gate import NoTestEvidence, check_test_evidence, read_floor, write_floor


def _report(
    path: Path, *, tests: int, failures: int = 0, errors: int = 0, skipped: int = 0
) -> Path:
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<testsuites><testsuite name="pytest" tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}" time="1.0"></testsuite></testsuites>\n',
        encoding="utf-8",
    )
    return path


def test_a_missing_report_is_a_refusal(tmp_path: Path) -> None:
    """No report means the test step did not run, whatever it returned."""
    with pytest.raises(NoTestEvidence, match="no test report"):
        check_test_evidence(tmp_path / "absent.xml", floor_path=tmp_path / "floor")


def test_a_run_that_collected_nothing_is_a_refusal(tmp_path: Path) -> None:
    """pytest exits 0 with `no tests ran` when testpaths points at an empty directory."""
    report = _report(tmp_path / "r.xml", tests=0)
    with pytest.raises(NoTestEvidence, match="collected 0 tests"):
        check_test_evidence(report, floor_path=tmp_path / "floor")


def test_failures_are_a_refusal_even_though_the_report_exists(tmp_path: Path) -> None:
    report = _report(tmp_path / "r.xml", tests=10, failures=2)
    with pytest.raises(NoTestEvidence, match="2 failed"):
        check_test_evidence(report, floor_path=tmp_path / "floor")


def test_collection_errors_are_a_refusal(tmp_path: Path) -> None:
    report = _report(tmp_path / "r.xml", tests=10, errors=1)
    with pytest.raises(NoTestEvidence, match="1 errored"):
        check_test_evidence(report, floor_path=tmp_path / "floor")


def test_a_healthy_run_returns_its_counts(tmp_path: Path) -> None:
    report = _report(tmp_path / "r.xml", tests=434, skipped=3)
    floor = tmp_path / "floor"
    evidence = check_test_evidence(report, floor_path=floor)
    assert evidence.collected == 434
    assert evidence.skipped == 3


def test_the_floor_ratchets_up_on_a_healthy_run(tmp_path: Path) -> None:
    """Growth is recorded so the next run cannot quietly shrink back."""
    floor = tmp_path / "floor"
    write_floor(floor, 100)
    check_test_evidence(_report(tmp_path / "r.xml", tests=150), floor_path=floor)
    assert read_floor(floor) == 150


def test_a_silent_drop_below_the_floor_is_a_refusal(tmp_path: Path) -> None:
    """Half the suite vanishing must not read as a green gate."""
    floor = tmp_path / "floor"
    write_floor(floor, 400)
    with pytest.raises(NoTestEvidence, match="floor"):
        check_test_evidence(_report(tmp_path / "r.xml", tests=200), floor_path=floor)


def test_the_floor_is_never_ratcheted_down_by_a_refused_run(tmp_path: Path) -> None:
    floor = tmp_path / "floor"
    write_floor(floor, 400)
    with pytest.raises(NoTestEvidence):
        check_test_evidence(_report(tmp_path / "r.xml", tests=200), floor_path=floor)
    assert read_floor(floor) == 400, "a refusal must not lower the bar for the next attempt"


def test_deleting_tests_requires_editing_the_committed_floor(tmp_path: Path) -> None:
    """The escape hatch exists, but it is a diff a reviewer sees rather than a quiet run."""
    floor = tmp_path / "floor"
    write_floor(floor, 400)
    write_floor(floor, 200)  # the deliberate, reviewable act
    evidence = check_test_evidence(_report(tmp_path / "r.xml", tests=200), floor_path=floor)
    assert evidence.collected == 200


def test_a_stale_report_from_an_earlier_run_is_not_evidence(tmp_path: Path) -> None:
    """The gate deletes the report first; a leftover must still be detectable as unfresh."""
    report = _report(tmp_path / "r.xml", tests=434)
    with pytest.raises(NoTestEvidence, match="older than"):
        check_test_evidence(
            report,
            floor_path=tmp_path / "floor",
            not_before=report.stat().st_mtime + 60,
        )


def test_the_projects_own_floor_is_committed() -> None:
    """The floor lives in git, not in a cache: a floor that resets on a clean checkout is not
    a ratchet."""
    floor = Path(__file__).resolve().parents[1] / "scripts" / "test-count.floor"
    assert floor.exists(), f"no committed test-count floor at {floor}"
    assert read_floor(floor) > 0
