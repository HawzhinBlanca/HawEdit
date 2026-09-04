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

import importlib
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from xml.etree import ElementTree

__all__ = [
    "GATE_TOOLS",
    "TARGET_COVERAGE_MODULES",
    "CoverageEvidence",
    "CoverageTracer",
    "ForeignTool",
    "NoTestEvidence",
    "TestEvidence",
    "assert_tools_are_from_this_environment",
    "check_coverage_evidence",
    "check_test_evidence",
    "get_executable_lines",
    "read_floor",
    "write_floor",
]


class NoTestEvidence(RuntimeError):
    """Raised when the test report does not prove a healthy run happened."""


class ForeignTool(RuntimeError):
    """Raised when a gate step would be run by something outside this environment."""


# The three third-party programs the gate's steps are. `hawedit` is deliberately absent: it is
# installed editable both here and in CI, so its file lives in the checkout rather than under
# `sys.prefix`, and requiring otherwise would refuse the only install layout this repo uses.
# That it imports at all is proved by this module running.
GATE_TOOLS: Final = ("pytest", "ruff", "mypy")


def assert_tools_are_from_this_environment(tools: tuple[str, ...] = GATE_TOOLS) -> None:
    """Refuse a gate whose tools were substituted from outside the interpreter's environment.

    D-092 closed the case where `PY` was not a Python that runs this project. It could not
    close this one: with a real `PY`, anything earlier on `sys.path` that answers to
    `-m pytest` becomes the test step. Measured — a 30-line `pytest/__main__.py` on
    `PYTHONPATH` wrote a clean 1,200-test JUnit report, and the gate printed `VERIFY OK` in
    four seconds having run nothing, **and ratcheted the committed floor from 1,155 to 1,200**,
    so every honest run after it would be refused for a bar a forgery invented.

    The rule is provenance, not a list of hostile environment variables — a list of ways to
    redirect an import is the same losing shape as the blacklist of no-op commands this
    module's docstring describes. `sys.prefix` is where the interpreter's own packages live, so
    a tool outside it is not the one the environment installed, whether it arrived via
    `PYTHONPATH`, user site-packages or a directory in the working tree. Nothing is chosen; the
    interpreter and the module settle it between them.

    Not closed, and not closeable here: a substituted `hawedit` itself. This check would then
    be the forgery's own code. Stated rather than implied — see D-093.

    Raises:
        ForeignTool: a tool is missing, has no file, or resolves outside `sys.prefix`.
    """
    prefix = Path(sys.prefix).resolve()
    foreign: list[str] = []
    for name in tools:
        try:
            module = importlib.import_module(name)
        except ImportError as exc:
            raise ForeignTool(
                f"{name} does not import in {prefix} — the gate cannot run a step whose "
                f"program is missing ({exc})."
            ) from exc
        origin = getattr(module, "__file__", None)
        if origin is None:
            # A namespace package: a bare directory named `pytest` on the path, with no
            # `__init__.py`. It imports, it has no file, and `Path(None)` would crash here
            # rather than refuse — which would read as a broken gate instead of a caught one.
            foreign.append(f"{name} -> a namespace package with no file")
            continue
        resolved = Path(origin).resolve()
        if not resolved.is_relative_to(prefix):
            foreign.append(f"{name} -> {resolved}")
    if foreign:
        raise ForeignTool(
            "these gate tools do not come from this interpreter's environment "
            f"({prefix}): {'; '.join(foreign)}. A step run by a substituted program proves "
            f"nothing about this project — check PYTHONPATH, user site-packages, and any "
            f"directory of that name in the working tree."
        )


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


TARGET_COVERAGE_MODULES: Final[tuple[str, ...]] = (
    "boundary.py",
    "captions.py",
    "clip.py",
    "delivery.py",
    "measure.py",
    "reframe.py",
    "render.py",
)


@dataclass(frozen=True, slots=True)
class CoverageEvidence:
    """Statement coverage evidence for the target modules."""

    total_covered: int
    total_executable: int
    by_module: dict[str, tuple[int, int]]  # name -> (covered, executable)

    @property
    def percentage(self) -> float:
        if not self.total_executable:
            return 0.0
        return (self.total_covered / self.total_executable) * 100.0


def get_executable_lines(code: types.CodeType) -> set[int]:
    """Recursively collect line numbers from CPython's bytecode line table (`co_lines`)."""
    lines: set[int] = set()
    for _, _, line in code.co_lines():
        if line is not None:
            lines.add(line)
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            lines |= get_executable_lines(const)
    return lines


class CoverageTracer:
    """Zero-dependency line coverage tracer scoped to target modules."""

    def __init__(self, target_names: tuple[str, ...] = TARGET_COVERAGE_MODULES) -> None:
        self.target_names: tuple[str, ...] = target_names
        self.covered_lines: dict[str, set[int]] = {name: set() for name in target_names}
        self._active: bool = False

    def _line_tracer(self, frame: types.FrameType, event: str, arg: Any) -> Any:
        if event == "line":
            fn = frame.f_code.co_filename
            for name in self.target_names:
                if fn.endswith(name):
                    self.covered_lines[name].add(frame.f_lineno)
                    break
        return self._line_tracer

    def _call_tracer(self, frame: types.FrameType, event: str, arg: Any) -> Any:
        if event == "call":
            fn = frame.f_code.co_filename
            for name in self.target_names:
                if fn.endswith(name):
                    return self._line_tracer
        return None

    def start(self) -> None:
        self.covered_lines = {name: set() for name in self.target_names}
        self._active = True
        sys.settrace(self._call_tracer)

    def stop(self) -> None:
        if self._active:
            sys.settrace(None)
            self._active = False

    def compute_evidence(self, project_root: Path) -> CoverageEvidence:
        total_covered = 0
        total_executable = 0
        by_module: dict[str, tuple[int, int]] = {}

        src_dir = project_root / "src" / "hawedit"
        for name in sorted(self.target_names):
            module_path = src_dir / name
            if not module_path.is_file():
                continue
            code = compile(module_path.read_text(encoding="utf-8"), str(module_path), "exec")
            executable = get_executable_lines(code)
            covered = self.covered_lines.get(name, set()) & executable
            cov_count = len(covered)
            exec_count = len(executable)
            total_covered += cov_count
            total_executable += exec_count
            by_module[name] = (cov_count, exec_count)

        return CoverageEvidence(
            total_covered=total_covered,
            total_executable=total_executable,
            by_module=by_module,
        )

    def save_report(self, report_path: Path, project_root: Path) -> CoverageEvidence:
        evidence = self.compute_evidence(project_root)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "total_covered": evidence.total_covered,
            "total_executable": evidence.total_executable,
            "percentage": round(evidence.percentage, 1),
            "by_module": {
                name: {
                    "covered": cov,
                    "executable": exc,
                    "pct": round((cov / exc * 100.0) if exc else 0.0, 1),
                }
                for name, (cov, exc) in evidence.by_module.items()
            },
        }
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return evidence


def check_coverage_evidence(
    report_path: Path,
    *,
    floor_path: Path,
    not_before: float | None = None,
) -> CoverageEvidence:
    """Read .gate/coverage-report.json and enforce the committed coverage floor.

    Raises:
        NoTestEvidence: if report missing, stale, invalid, or coverage drops below floor.
    """
    if not report_path.is_file():
        raise NoTestEvidence(
            f"no coverage report at {report_path}. The test step exited without writing coverage "
            f"evidence for core delivery modules."
        )

    if not_before is not None and report_path.stat().st_mtime < not_before:
        raise NoTestEvidence(
            f"{report_path} is older than this run started. It is a leftover from an earlier run, "
            f"not evidence about this one."
        )

    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise NoTestEvidence(
            f"{report_path} is not valid JSON ({exc}). Coverage evidence is corrupt."
        ) from exc

    try:
        total_covered = int(data["total_covered"])
        total_executable = int(data["total_executable"])
        by_module_raw = data["by_module"]
        by_module = {
            name: (int(stats["covered"]), int(stats["executable"]))
            for name, stats in by_module_raw.items()
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise NoTestEvidence(f"{report_path} does not match the expected schema ({exc}).") from exc

    evidence = CoverageEvidence(
        total_covered=total_covered,
        total_executable=total_executable,
        by_module=by_module,
    )

    floor = read_floor(floor_path)
    if evidence.total_covered < floor:
        raise NoTestEvidence(
            f"only {evidence.total_covered} statements covered in core modules against a floor "
            f"of {floor} ({evidence.percentage:.1f}% across {evidence.total_executable} "
            f"statements). Either tests were deleted, or untested code was added to the "
            f"7 core modules. If intentional, edit scripts/coverage.floor in the same commit."
        )

    if evidence.total_covered > floor:
        write_floor(floor_path, evidence.total_covered)

    return evidence


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
    require_no_skips: bool = False,
) -> TestEvidence:
    """Read the report back and refuse anything that is not a healthy, complete run.

    Args:
        report_path: the `--junitxml` report the gate just asked pytest to write.
        floor_path: committed file holding the lowest acceptable collected-test count. It is
            ratcheted upward here when the suite has grown.
        not_before: if given, the report must be at least this new (a POSIX mtime). The gate
            deletes the report before running, so a leftover should be impossible — this
            catches the case where the delete silently failed.
        require_no_skips: if True, refuse any report containing skipped tests (> 0).

    Returns:
        The counts, once they have been accepted.

    Raises:
        NoTestEvidence: no report, a stale report, zero tests collected, any failure or
            error, any skipped test when require_no_skips is True, or a count below floor.
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

    if require_no_skips and evidence.skipped > 0:
        raise NoTestEvidence(
            f"{report_path} says {evidence.skipped} test(s) skipped — skipped tests are "
            f"refused under the zero-skip policy."
        )

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
    # Measured 2026-08-09: this fix was described here at length and held in place by nothing.
    # Substituting `collected` for `passed` in the ratchet below left all 1,164 tests green,
    # because every ratchet test used a report with `skipped=0` — where the two numbers are equal
    # by construction — and this host skips nothing. The defect is invisible exactly here and
    # fires on a machine where something legitimately skips. Now pinned by the idempotence
    # property in `tests/test_gate_evidence.py`: a green run must never leave the gate refusing
    # an identical one. D-095.
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
    """`python -m hawedit.gate <report.xml> <floor> [not_before] [options]`.

    Options: `--require-no-skips`, `--coverage-floor <path>`, `--coverage-report <path>`.

    Also `python -m hawedit.gate --check-tools`, which `verify.sh` runs before any step: it
    proves in one call that the interpreter runs this project (it is this module) and that the
    programs the steps consist of came from the interpreter's own environment.
    """
    if argv[1:2] == ["--check-tools"]:
        try:
            assert_tools_are_from_this_environment()
        except ForeignTool as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 7
        # `verify.sh` matches on this value, not on the exit code — an exit code is exactly
        # what a no-op interpreter is good at (D-092).
        print("hawedit-interpreter-ok")
        return 0

    require_no_skips = False
    coverage_floor: Path | None = None
    coverage_report: Path | None = None
    positional: list[str] = []

    idx = 1
    while idx < len(argv):
        arg = argv[idx]
        if arg == "--require-no-skips":
            require_no_skips = True
            idx += 1
        elif arg == "--coverage-floor" and idx + 1 < len(argv):
            coverage_floor = Path(argv[idx + 1])
            idx += 2
        elif arg == "--coverage-report" and idx + 1 < len(argv):
            coverage_report = Path(argv[idx + 1])
            idx += 2
        else:
            positional.append(arg)
            idx += 1

    if not 2 <= len(positional) <= 3:
        print(
            "usage: python -m hawedit.gate <report.xml> <floor> [not_before] "
            "[--require-no-skips] [--coverage-floor <path>] [--coverage-report <path>]",
            file=sys.stderr,
        )
        return 64

    not_before = float(positional[2]) if len(positional) == 3 else None
    try:
        evidence = check_test_evidence(
            Path(positional[0]),
            floor_path=Path(positional[1]),
            not_before=not_before,
            require_no_skips=require_no_skips,
        )
    except NoTestEvidence as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 6

    print(
        f"test evidence OK — {evidence.collected} collected, {evidence.passed} passed, "
        f"{evidence.skipped} skipped"
    )

    if coverage_floor is not None and coverage_report is not None:
        try:
            cov = check_coverage_evidence(
                coverage_report, floor_path=coverage_floor, not_before=not_before
            )
        except NoTestEvidence as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 6
        print(
            f"coverage evidence OK — {cov.total_covered} / {cov.total_executable} statements "
            f"({cov.percentage:.1f}%)"
        )

    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through verify.sh
    raise SystemExit(main(sys.argv))
