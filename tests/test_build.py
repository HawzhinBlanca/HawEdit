"""The wheel is reproducible, so a digest can identify this code rather than one build.

`AUDIT_REPORT.md` quotes the wheel's byte count and deliberately no SHA-256, because two
`pip wheel` runs at one unchanged commit produced the same size and different hashes — nothing set
`SOURCE_DATE_EPOCH`, so every ZIP entry carried the mtime of the moment it was written. Measured
2026-08-09 before the fix: `a7c3b2f1c280aff4` and `38d1d2475c46e120` for the same tree.

`scripts/build-wheel.sh` takes the epoch from the commit's own author date — derived, never
invented — and refuses outside a git checkout rather than substituting `now`, which would restore
the behaviour silently. That refusal is not exercised here: the script resolves the repository from
its own location, so reaching the no-commit branch would mean copying the tree out of git, which
costs more than the branch is worth. It is three lines and it fails closed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-wheel.sh"

BASH = shutil.which("bash")

needs_build = pytest.mark.skipif(
    BASH is None or shutil.which("git") is None, reason="needs bash and git"
)


def build(out: Path) -> Path:
    assert BASH is not None
    done = subprocess.run(
        # The resolved path, not the name: on Windows `subprocess` searches the system PATH
        # and finds WSL's `bash.exe`, which cannot open a `C:/…` path at all — measured, it
        # reports the script as "No such file or directory" while Git Bash runs it fine. And
        # POSIX form for the arguments, because bash eats the backslashes in `C:\Users\…`.
        [BASH, SCRIPT.as_posix(), out.as_posix()],
        capture_output=True,
        text=True,
        errors="replace",
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    wheels = sorted(out.glob("hawedit-*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


def commit_epoch() -> int:
    return int(
        subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        ).stdout.strip()
    )


@needs_build
def test_two_builds_of_one_commit_are_byte_identical(tmp_path: Path) -> None:
    """The promise a quoted digest would rest on, checked on the two artifacts."""
    first = hashlib.sha256(build(tmp_path / "a").read_bytes()).hexdigest()
    second = hashlib.sha256(build(tmp_path / "b").read_bytes()).hexdigest()
    assert first == second, f"{first} != {second}"


@needs_build
def test_every_entry_carries_the_commits_timestamp_not_the_clock(tmp_path: Path) -> None:
    """The control, and the reason the test above passes.

    Two builds being equal is also what a build system that happened to be deterministic today
    would produce, so equality alone would let the epoch be deleted unnoticed — and a test whose
    control is "setuptools is non-deterministic" would break the day that stops being true. This
    asserts the mechanism instead: every ZIP entry is stamped with the commit, in UTC, which is
    false the moment the epoch stops being set.
    """
    # ZIP stores the second as `sec // 2`, so every stamp it can hold is an even second. The
    # first version of this compared against the raw epoch and passed here only because HEAD
    # happened to carry an even timestamp; CI's commit was odd and it failed by exactly one
    # second. Rounding down is not a tolerance — it is the value the format can represent, and
    # a clock-based mtime is wrong by far more than a second in every entry.
    epoch = commit_epoch()
    epoch -= epoch % 2
    expected = dt.datetime.fromtimestamp(epoch, tz=dt.UTC).timetuple()[:6]
    with zipfile.ZipFile(build(tmp_path / "c")) as archive:
        stamps = {info.date_time for info in archive.infolist()}
    assert stamps == {expected}, f"{sorted(stamps)} != {expected}"


# --- D-169: the report says "the wheel contains", and only the tree was ever checked ---------


def _wheel_contents_claim() -> str:
    """AUDIT_REPORT's wheel-contents bullet, on its own."""
    section = (ROOT / "AUDIT_REPORT.md").read_text(encoding="utf-8")
    section = section.split("## Verification evidence")[1]
    bullet = next(b for b in section.split("\n- ") if b.startswith("Wheel contains"))
    return bullet.split("\n- ")[0]


def _paths_the_report_claims() -> set[str]:
    """The files that bullet names, read out of the claim rather than copied beside it."""
    return set(re.findall(r"`([\w./-]+\.[A-Za-z0-9]+)`", _wheel_contents_claim()))


@needs_build
def test_the_wheel_contains_every_file_the_audit_report_says_it_does(tmp_path: Path) -> None:
    """ "Wheel contains the Kurdish font/OFL, model-source manifest, WSL worker and setup
    module … verified by listing the archive."

    `test_claims.py` checks those paths exist **in the tree**, which its own docstring says: a
    claim about a wheel nobody can build from here. The tree is not the wheel. `assets/` and
    `models/` are not packages — they reach the wheel only through
    `[tool.setuptools.data-files]`, so deleting four lines of pyproject leaves every existing
    test green and ships a wheel with no font, no OFL licence and no pinned revisions.

    Measured on the real artifact: 55 entries, and the four data files land under
    `hawedit-0.1.0.data/data/share/hawedit/…`, so the match is on the path's tail — the claim is
    that the file ships, not where a wheel chooses to put it.
    """
    claimed = _paths_the_report_claims()
    # Non-vacuity from a different file than the one being parsed: OFL-1.1 requires the licence
    # to accompany the font, `registry.SHIPPED_ASSETS` records that obligation with the path,
    # and the thing that actually ships is this archive. A reworded bullet that stopped naming
    # it would fail here rather than quietly checking nothing.
    from hawedit.registry import SHIPPED_ASSETS

    obliged = {asset.licence_file for asset in SHIPPED_ASSETS if asset.licence_file}
    assert obliged and obliged <= claimed, (
        f"the wheel-contents claim no longer names the licence files this project is obliged "
        f"to ship: {sorted(obliged - claimed)}"
    )

    with zipfile.ZipFile(build(tmp_path / "contents")) as archive:
        names = archive.namelist()
    missing = [path for path in sorted(claimed) if not any(n.endswith(path) for n in names)]
    assert not missing, (
        f"AUDIT_REPORT says the wheel contains these and it does not: {missing}. The files are "
        f"in the tree — check [tool.setuptools.data-files] in pyproject.toml."
    )
