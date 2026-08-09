"""The local wheel candidate is reproducible under one measured builder identity.

The script snapshots one clean Git object twice, provisions the exact hash-locked build frontend
and backend into a private venv, and refuses to publish unless both independent wheels match. The
production release path adds exact-SHA CI evidence, provenance, SBOM and attestation.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-wheel.sh"


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


@pytest.fixture(scope="module")
def committed_builds(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[tuple[Path, dict[str, object]], tuple[Path, dict[str, object]]]:
    if BASH is None or shutil.which("git") is None:
        pytest.skip("needs bash and git")
    root = tmp_path_factory.mktemp("locked-wheel-builds")
    return build(root / "a"), build(root / "b")


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
