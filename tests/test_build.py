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
    expected = dt.datetime.fromtimestamp(commit_epoch(), tz=dt.UTC).timetuple()[:6]
    with zipfile.ZipFile(build(tmp_path / "c")) as archive:
        stamps = {info.date_time for info in archive.infolist()}
    assert stamps == {expected}, sorted(stamps)
