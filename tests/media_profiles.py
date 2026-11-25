"""Explicit, source-specific real-media admission; historical identities stay pinned."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST = Path(__file__).parent / "media" / "current-provenance.json"
LEGACY_NAME = "ep29-chunk50min.mp4"


class MediaProfileError(ValueError):
    """Configured test media cannot establish its recorded identity."""


def select_media_profile(root: Path, profile: str = "auto") -> str:
    if profile not in {"auto", "legacy-ep29", "current-zar"}:
        raise MediaProfileError(f"Unknown HAWEDIT_MEDIA_PROFILE: {profile}")
    if not root.is_dir():
        raise MediaProfileError(f"Real-media root does not exist: {root}")
    if profile != "auto":
        return profile
    return "legacy-ep29" if (root / LEGACY_NAME).is_file() else "current-zar"


def current_media_records() -> tuple[dict[str, Any], ...]:
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if document["schema"] != 1 or document["profile"] != "current-zar":
        raise MediaProfileError("Unsupported current-media manifest")
    return tuple(document["records"])


def validate_current_media(root: Path, record: dict[str, Any]) -> Path:
    relative = record["path"]
    if not isinstance(relative, str):
        raise MediaProfileError("Media manifest paths must be strings")
    parts = PurePosixPath(relative)
    if (
        not isinstance(relative, str)
        or parts.is_absolute()
        or ".." in parts.parts
        or "\\" in relative
        or ":" in relative
    ):
        raise MediaProfileError("Media manifest paths must remain relative to the configured root")
    bound_root = root.resolve(strict=True)
    try:
        path = (bound_root / relative).resolve(strict=True)
        if not path.is_relative_to(bound_root) or not path.is_file():
            raise MediaProfileError("Media path escaped its configured root")
        before = path.stat()
        if before.st_size != record["size_bytes"]:
            raise MediaProfileError(f"Media size mismatch: {relative}")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = path.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or digest != record["sha256"]:
            raise MediaProfileError(f"Media digest or file identity mismatch: {relative}")
        return path
    except OSError as exc:
        raise MediaProfileError(f"Pinned current media unavailable: {relative}: {exc}") from exc
