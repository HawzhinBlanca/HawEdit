"""Positive evidence that the test step actually ran — audit finding #5.

`verify.sh` used to trust two things it had no business trusting: that a step command was a
real command, and that exit 0 meant work happened. It defended the first with a blacklist of
five spellings of "do nothing" (`true`, `:`, `/bin/true`, …), which `TEST_CMD="echo skipped"`
walked straight past to print `VERIFY OK` having run zero tests. It never defended the second
at all.

Both are now closed, in opposite directions:

* **Deliberate bypass** — the gate refuses to run at all if any step command is overridden.
  That is a whitelist of one (the gate's own commands), which is the only kind of list that
  can be complete. It lives in `verify.sh` because it must apply before anything executes.
* **Accidental silence** — this module. A `testpaths` typo, a stray `-k` in `addopts`, a
  plugin that swallows a collection error: pytest exits 0 having run nothing, and no rule
  about *commands* catches it, because the command was right. So the gate deletes the report,
  runs pytest under `--junitxml`, and reads the report back. Exit code is not evidence; the
  report is.

The floor ratchets on the number of tests that actually **ran**, which is also the number it
gates on. Growth is recorded automatically; shrinkage is refused. Deleting tests stays possible
— you edit the committed number — but it becomes a line in a diff a reviewer sees, rather than
a suite that quietly got smaller between two green runs.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

__all__ = [
    "NoTestEvidence",
    "TestEvidence",
    "check_test_evidence",
    "read_floor",
    "write_floor",
]


class NoTestEvidence(RuntimeError):
    """Raised when the test report does not prove a healthy run happened."""


@dataclass(frozen=True, slots=True)
class TestEvidence:
    """What the report says actually happened."""

    collected: int
    skipped: int
    failures: int
    errors: int

    @property
    def passed(self) -> int:
        return self.collected - self.skipped - self.failures - self.errors


def read_floor(path: Path) -> int:
    """The lowest collected-test count this project accepts. Missing floor reads as 0."""
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8").strip()
    return int(text) if text else 0


def write_floor(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{count}\n", encoding="utf-8")


def _parse(report_path: Path) -> TestEvidence:
    try:
        root = ElementTree.parse(report_path).getroot()
    except ElementTree.ParseError as exc:
        raise NoTestEvidence(
            f"{report_path} is not readable as a JUnit report ({exc}). The test step wrote "
            f"something, but not evidence."
        ) from exc

    suites = list(root.iter("testsuite"))
    if not suites:
        raise NoTestEvidence(f"{report_path} contains no <testsuite> element — collected 0 tests.")

    def total(attr: str) -> int:
        return sum(int(suite.get(attr) or 0) for suite in suites)

    return TestEvidence(
        collected=total("tests"),
        skipped=total("skipped"),
        failures=total("failures"),
        errors=total("errors"),
    )


def check_test_evidence(
    report_path: Path,
    *,
    floor_path: Path,
    not_before: float | None = None,
) -> TestEvidence:
    """Read the report back and refuse anything that is not a healthy, complete run.

    Args:
        report_path: the `--junitxml` report the gate just asked pytest to write.
        floor_path: committed file holding the lowest acceptable collected-test count. It is
            ratcheted upward here when the suite has grown.
        not_before: if given, the report must be at least this new (a POSIX mtime). The gate
            deletes the report before running, so a leftover should be impossible — this
            catches the case where the delete silently failed.

    Returns:
        The counts, once they have been accepted.

    Raises:
        NoTestEvidence: no report, a stale report, zero tests collected, any failure or
            error, or a collected count below the committed floor.
    """
    if not report_path.exists():
        raise NoTestEvidence(
            f"no test report at {report_path}. The test step exited without writing one, so "
            f"there is no evidence any test ran — and an exit code is not evidence."
        )

    if not_before is not None and report_path.stat().st_mtime < not_before:
        raise NoTestEvidence(
            f"{report_path} is older than this run started. It is a leftover from an earlier "
            f"run, not evidence about this one."
        )

    evidence = _parse(report_path)

    if evidence.collected == 0:
        raise NoTestEvidence(
            f"{report_path} says the run collected 0 tests. pytest exits 0 when it finds "
            f"nothing to run — check testpaths, a stray -k filter, or a collection error."
        )
    if evidence.failures or evidence.errors:
        raise NoTestEvidence(
            f"{evidence.failures} failed, {evidence.errors} errored out of "
            f"{evidence.collected} collected."
        )

    # Collected is not run. A report of 700 collected, 0 failures, 0 errors and 700 *skipped*
    # cleared every check this function had, and `verify.sh` printed VERIFY OK with zero test
    # bodies executed. One over-broad `skipif` — a media guard that evaluates true everywhere —
    # produces exactly that report. The gate had learned that an exit code is not evidence and
    # then accepted a report proving nothing ran. Found by the independent review.
    if evidence.passed == 0:
        raise NoTestEvidence(
            f"{report_path} says {evidence.collected} tests were collected and {evidence.skipped} "
            f"skipped — nothing actually ran. A suite that skips itself is not a passing suite."
        )

    # One number, gated and ratcheted: tests that actually RAN. Ratcheting on `collected` while
    # gating on `passed` made the gate poison itself — one legitimately skipped test (a symlink
    # a Windows account may not create) collected 873 and passed 872, so the first run raised
    # the floor to 873 and every run after it was refused for missing a bar the previous run
    # invented. Two floors, one job, and they disagreed on any host with a skip.
    floor = read_floor(floor_path)
    if evidence.passed < floor:
        raise NoTestEvidence(
            f"only {evidence.passed} tests passed against a floor of {floor} "
            f"({evidence.skipped} skipped of {evidence.collected} collected). Either "
            f"{floor - evidence.passed} test(s) disappeared, or a skip condition is creeping. "
            f"If ffmpeg or the media stack is missing, install it: `bash scripts/setup.sh`. If "
            f"the removal is intentional, lower the floor in the same commit that removes them "
            f"— a shrinking suite must be a visible edit, not a quieter green run."
        )
    if evidence.passed > floor:
        write_floor(floor_path, evidence.passed)

    return evidence


def main(argv: list[str]) -> int:
    """`python -m hawedit.gate <report.xml> <floor> [<not_before_mtime>]`."""
    if not 3 <= len(argv) <= 4:
        print("usage: python -m hawedit.gate <report.xml> <floor> [not_before]", file=sys.stderr)
        return 64
    not_before = float(argv[3]) if len(argv) == 4 else None
    try:
        evidence = check_test_evidence(
            Path(argv[1]), floor_path=Path(argv[2]), not_before=not_before
        )
    except NoTestEvidence as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 6
    print(
        f"test evidence OK — {evidence.collected} collected, {evidence.passed} passed, "
        f"{evidence.skipped} skipped"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through verify.sh
    raise SystemExit(main(sys.argv))
