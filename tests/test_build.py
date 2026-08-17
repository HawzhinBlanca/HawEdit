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
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


SCRIPT = ROOT / "scripts" / "build-wheel.sh"


BASH = shutil.which("bash")


needs_build = pytest.mark.skipif(
    BASH is None or shutil.which("git") is None, reason="needs bash and git"
)


def build(out: Path) -> tuple[Path, dict[str, object]]:
    assert BASH is not None
    done = subprocess.run(
        # Use the resolved Git Bash path and POSIX-form arguments: Windows command lookup can
        # otherwise select WSL's launcher, and bash consumes backslashes in C:\ paths.
        [BASH, SCRIPT.as_posix(), out.as_posix()],
        capture_output=True,
        text=True,
        errors="replace",
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    wheels = sorted(out.glob("hawedit-*.whl"))
    assert len(wheels) == 1, wheels
    report = json.loads(done.stdout)
    assert report["wheel"] == str(wheels[0].resolve())
    return wheels[0], report


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
def test_two_builds_of_one_commit_are_byte_identical(
    committed_builds: tuple[tuple[Path, dict[str, object]], tuple[Path, dict[str, object]]],
) -> None:
    """Both independent invocations identify exactly the same wheel bytes."""
    first = hashlib.sha256(committed_builds[0][0].read_bytes()).hexdigest()
    second = hashlib.sha256(committed_builds[1][0].read_bytes()).hexdigest()
    assert first == second, f"{first} != {second}"


@needs_build
def test_every_entry_carries_the_commits_timestamp_not_the_clock(
    committed_builds: tuple[tuple[Path, dict[str, object]], tuple[Path, dict[str, object]]],
) -> None:
    """The archive timestamp is derived from the Git object, not the wall clock."""
    # ZIP stores the second as `sec // 2`, so the exact representable value is even.
    epoch = commit_epoch()
    epoch -= epoch % 2
    expected = dt.datetime.fromtimestamp(epoch, tz=dt.UTC).timetuple()[:6]
    with zipfile.ZipFile(committed_builds[0][0]) as archive:
        stamps = {info.date_time for info in archive.infolist()}
    assert stamps == {expected}, f"{sorted(stamps)} != {expected}"


def _wheel_contents_claim() -> str:
    """AUDIT_REPORT's wheel-contents bullet, on its own."""
    section = (ROOT / "AUDIT_REPORT.md").read_text(encoding="utf-8")
    section = section.split("## Verification evidence")[1]
    bullet = next(b for b in section.split("\n- ") if b.startswith("Wheel contains"))
    return bullet.split("\n- ")[0]


def _paths_the_report_claims() -> set[str]:
    """The files that bullet names, read out of the claim rather than copied beside it."""
    return set(re.findall(r"`([\w./-]+\.[A-Za-z0-9]+)`", _wheel_contents_claim()))


"""The local wheel candidate is reproducible under one measured builder identity.

The script snapshots one clean Git object twice, provisions the exact hash-locked build frontend
and backend into a private venv, and refuses to publish unless both independent wheels match. The
production release path adds exact-SHA CI evidence, provenance, SBOM and attestation.
"""


def _bash() -> str | None:
    """Prefer Git Bash on Windows; command lookup commonly returns the WSL launcher."""
    candidates: list[Path] = []
    if configured := os.environ.get("HAWEDIT_BASH"):
        candidates.append(Path(configured))
    if git := shutil.which("git"):
        candidates.append(Path(git).resolve().parent.parent / "bin" / "bash.exe")
    if program_files := os.environ.get("PROGRAMFILES"):
        candidates.append(Path(program_files) / "Git" / "bin" / "bash.exe")
    if local_app_data := os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(local_app_data) / "Programs" / "Git" / "bin" / "bash.exe")
    if sys.platform != "win32" and (found := shutil.which("bash")):
        candidates.append(Path(found))
    return next((str(candidate) for candidate in candidates if candidate.is_file()), None)


BASH = _bash()


@pytest.fixture(scope="module")
def committed_builds(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[tuple[Path, dict[str, object]], tuple[Path, dict[str, object]]]:
    if BASH is None or shutil.which("git") is None:
        pytest.skip("needs bash and git")
    root = tmp_path_factory.mktemp("locked-wheel-builds")
    return build(root / "a"), build(root / "b")


@needs_build
def test_build_script_reports_the_hash_locked_private_builder(
    committed_builds: tuple[tuple[Path, dict[str, object]], tuple[Path, dict[str, object]]],
) -> None:
    first = committed_builds[0][1]
    second = committed_builds[1][1]
    assert first["build_frontend"] == second["build_frontend"] == "pip==26.2.1"
    assert first["build_backend"] == second["build_backend"] == "setuptools==84.0.0"
    assert first["build_lock_sha256"] == second["build_lock_sha256"]
    assert first["revision"] == second["revision"]
    assert first["source_date_epoch"] == second["source_date_epoch"] == commit_epoch()
    assert first["sha256"] == second["sha256"]


def test_the_wheel_contains_every_file_the_audit_report_says_it_does(tmp_path: Path) -> None:
    """ "Wheel contains the Kurdish font/OFL, model-source manifest, WSL worker and setup
    module … verified by listing the archive."

    `test_claims.py` checks those paths exist **in the tree**, which its own docstring says: a
    claim about a wheel nobody can build from here. The tree is not the wheel. `assets/` and
    `models/` are not packages - they reach the wheel only through
    `[tool.setuptools.data-files]`, so deleting four lines of pyproject leaves every existing
    test green and ships a wheel with no font, no OFL licence and no pinned revisions.

    Measured on the real artifact: 55 entries, and the four data files land under
    `hawedit-0.1.0.data/data/share/hawedit/…`, so the match is on the path's tail - the claim is
    that the file ships, not where a wheel chooses to put it.

    Kept across the readiness merge, which has no counterpart for it. `build` there returns the
    wheel and its measured metadata rather than a bare path, so only the unpacking changed.
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

    wheel, _metadata = build(tmp_path / "contents")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    missing = [path for path in sorted(claimed) if not any(n.endswith(path) for n in names)]
    assert not missing, (
        f"AUDIT_REPORT says the wheel contains these and it does not: {missing}. The files are "
        f"in the tree - check [tool.setuptools.data-files] in pyproject.toml."
    )
