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


def test_a_report_with_no_testsuite_element_is_a_refusal(tmp_path: Path) -> None:
    """The one refusal in gate.py that no test held — measured by neutralising each in a shadow
    copy of src/hawedit and running this file with tests/test_gate.py and tests/test_claims.py.

    Well-formed XML that parses and carries no `<testsuite>` is the gap between "the test step
    wrote something" and "the test step wrote evidence". Every count `check_test_evidence`
    derives is a sum over the suites it finds, so with none the totals are all zero and the
    refusal one line down — `collected == 0` — would catch it too. This is the earlier and more
    exact answer: the file is not a report at all, rather than a report of nothing.
    """
    empty = tmp_path / "r.xml"
    empty.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<testsuites></testsuites>\n', encoding="utf-8"
    )
    with pytest.raises(NoTestEvidence, match="no <testsuite> element"):
        check_test_evidence(empty, floor_path=tmp_path / "floor")


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


# --- D-095: the gate's own self-poisoning fix was held in place by nothing -------------------


def test_the_ratchet_writes_what_ran_not_what_was_collected(tmp_path: Path) -> None:
    """`gate.py` describes this fix at length and no test held it.

    Measured: substituting `collected` for `passed` in the ratchet alone left all 1,164 tests
    green. Every ratchet test used a report with `skipped=0`, where the two numbers are equal by
    construction, and this host skips nothing — so the defect is invisible exactly here and
    fires on a machine where something legitimately skips.

    Asserted on the artifact: the committed floor file, not the returned counts.
    """
    floor = tmp_path / "floor"
    write_floor(floor, 800)
    check_test_evidence(_report(tmp_path / "r.xml", tests=873, skipped=1), floor_path=floor)
    assert read_floor(floor) == 872, (
        "the floor recorded a number no run achieved — 873 collected, 872 passed, and a bar of "
        "873 refuses the very run that set it"
    )


def test_a_run_with_a_skip_does_not_poison_the_next_identical_run(tmp_path: Path) -> None:
    """The property, stated the way it actually failed: 873 collected, 872 passed, then red.

    This is the strongest form of the check, because it needs no knowledge of which number is
    right — it says only that a green run must not leave the gate refusing an identical one. A
    ratchet on `collected` fails it; a ratchet on `passed` cannot.
    """
    floor = tmp_path / "floor"
    report = _report(tmp_path / "r.xml", tests=873, skipped=1)
    first = check_test_evidence(report, floor_path=floor)
    second = check_test_evidence(report, floor_path=floor)  # must not raise
    assert first.passed == second.passed == 872
    assert read_floor(floor) == 872


def test_the_floor_still_reaches_the_full_count_when_nothing_skips(tmp_path: Path) -> None:
    """The control. "Ratchet on `passed`" must not be read as "ratchet lower than collected".

    With no skips the two numbers are the same and the floor has to reach it, or a suite that
    skips nothing would be ratcheted below its own size and the gate would stop noticing
    deletions — the failure the ratchet exists to prevent, arrived at from the other side.
    """
    floor = tmp_path / "floor"
    check_test_evidence(_report(tmp_path / "r.xml", tests=1164), floor_path=floor)
    assert read_floor(floor) == 1164


# --- M0.1 audit: the zero-passed guard is load-bearing only where nothing tested it -----------
#
# `if evidence.passed == 0` exists because a report of "700 collected, 700 skipped" cleared every
# other check and `verify.sh` printed VERIFY OK with no test bodies executed. Measured: replacing
# it with `passed < 0` left the whole gate suite green, because every existing test supplies a
# non-zero floor — and at a non-zero floor the *floor* check refuses first. The one state where
# this guard is the only thing standing is a floor of 0, which `read_floor` returns for a missing
# or empty file, and no test paired the two. With the guard neutered and the floor absent:
#
#     ACCEPTED — collected 700, skipped 700, passed 0
#
# `evidence/the-gate-guard-that-only-matters-when-the-floor-is-zero.md`.
# =========================================================================================


@pytest.mark.parametrize("floor_state", ["missing", "empty", "whitespace"])
def test_a_wholly_skipped_run_is_refused_even_with_no_floor_to_lean_on(
    tmp_path: Path, floor_state: str
) -> None:
    """The floor cannot help here — it reads as 0 — so this guard is the only refusal left."""
    floor = tmp_path / "floor"
    if floor_state == "empty":
        floor.write_text("", encoding="utf-8")
    elif floor_state == "whitespace":
        floor.write_text("  \n", encoding="utf-8")
    assert read_floor(floor) == 0, "this test's premise is a floor that cannot refuse anything"

    report = _report(tmp_path / "r.xml", tests=700, skipped=700)
    with pytest.raises(NoTestEvidence, match="nothing actually ran"):
        check_test_evidence(report, floor_path=floor)


def test_a_healthy_run_is_still_accepted_with_no_floor(tmp_path: Path) -> None:
    """The control, and the table above needs one: a gate that refused every zero-floor run —
    or refused every report with any skip in it — would pass all three cases above.

    One skip out of 700 is a legitimate run, and it must ratchet the floor to what actually ran.
    """
    floor = tmp_path / "floor"
    evidence = check_test_evidence(
        _report(tmp_path / "r.xml", tests=700, skipped=1), floor_path=floor
    )
    assert (evidence.collected, evidence.skipped, evidence.passed) == (700, 1, 699)
    assert read_floor(floor) == 699, "the floor must ratchet on what ran, not on what was collected"
