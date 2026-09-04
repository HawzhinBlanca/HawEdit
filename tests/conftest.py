"""Pytest conftest hook for HawEdit statement coverage tracing and test tiers."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import pytest

from hawedit.gate import CoverageTracer

_tracer = CoverageTracer()

PINNED_EP29_CHUNK50MIN_SHA256 = "47235f4251961518d9bbae1ecbda9c7f5166c5baa57a2be98f5ec0eb64e6f863"
PINNED_EP29_CHUNK50MIN_NAME = "ep29-chunk50min.mp4"


def pytest_sessionstart(session: Any) -> None:
    _tracer.start()


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    _tracer.stop()
    root = Path(session.config.rootdir)
    gate_dir = root / ".gate"
    _tracer.save_report(gate_dir / "coverage-report.json", root)


def pytest_ignore_collect(collection_path: Any, config: Any = None) -> bool | None:
    """Ignore tests/media during collection when HAWEDIT_MEDIA_ROOT is unset.

    Preserves the zero-skip invariant for clean CI runs while failing (never skipping)
    when the environment variable is configured and the media file is missing or invalid.
    """
    path_obj = Path(str(collection_path)) if collection_path is not None else None
    if (
        path_obj is not None
        and ("tests" in path_obj.parts or path_obj.name == "media")
        and "media" in path_obj.parts
    ):
        media_root = os.environ.get("HAWEDIT_MEDIA_ROOT", "").strip()
        if not media_root:
            return True
    return None


def resolve_and_validate_media_file(media_root: Path) -> Path:
    """Resolve and cryptographically bind the canonical ep29-chunk50min.mp4 fixture.

    Enforces Task T1.4 invariant: FAILS (never skips) if file is missing or SHA-256 differs.
    """
    video_path = media_root / PINNED_EP29_CHUNK50MIN_NAME
    if not video_path.is_file():
        pytest.fail(
            f"HAWEDIT_MEDIA_ROOT is set to {media_root}, but {PINNED_EP29_CHUNK50MIN_NAME} "
            f"was not found at {video_path}."
        )

    h = hashlib.sha256()
    with video_path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    digest = h.hexdigest()

    if digest != PINNED_EP29_CHUNK50MIN_SHA256:
        pytest.fail(
            f"Cryptographic digest mismatch for {video_path}:\n"
            f"  Expected: {PINNED_EP29_CHUNK50MIN_SHA256}\n"
            f"  Actual:   {digest}\n"
            f"Refusing test execution on unverified media fixture."
        )

    return video_path


@pytest.fixture(scope="session")
def media_root() -> Path:
    """Resolve and validate the HAWEDIT_MEDIA_ROOT directory."""
    raw = os.environ.get("HAWEDIT_MEDIA_ROOT", "").strip()
    if not raw:
        pytest.fail("HAWEDIT_MEDIA_ROOT environment variable is not configured.")
    path = Path(raw).resolve()
    if not path.is_dir():
        pytest.fail(f"HAWEDIT_MEDIA_ROOT directory does not exist: {path}")
    return path


@pytest.fixture(scope="session")
def ep29_chunk50min(media_root: Path) -> Path:
    """Fixture returning validated canonical video path."""
    return resolve_and_validate_media_file(media_root)
