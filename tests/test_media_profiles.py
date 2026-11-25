"""Real-media profile selection and integrity refusals are tested without private media."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from media_profiles import (
    MediaProfileError,
    current_media_records,
    select_media_profile,
    validate_current_media,
)


def test_current_root_selects_current_profile_without_renaming_legacy_identity(
    tmp_path: Path,
) -> None:
    assert select_media_profile(tmp_path) == "current-zar"
    (tmp_path / "ep29-chunk50min.mp4").write_bytes(
        b"legacy identity is checked by its own resolver"
    )
    assert select_media_profile(tmp_path) == "legacy-ep29"
    assert select_media_profile(tmp_path, "current-zar") == "current-zar"


def test_media_profile_rejects_missing_root_and_unknown_profile(tmp_path: Path) -> None:
    with pytest.raises(MediaProfileError, match="does not exist"):
        select_media_profile(tmp_path / "missing")
    with pytest.raises(MediaProfileError, match="Unknown"):
        select_media_profile(tmp_path, "anything")


def test_current_manifest_preserves_the_documented_source_hashes() -> None:
    records = current_media_records()
    assert len(records) == 4
    assert len({r["path"] for r in records}) == 4
    assert (
        records[0]["sha256"] == "17a547016e05c1748a17ec59dc183cd7b1808387f1d7df1efdfd375cc0b1ec72"
    )
    assert (
        records[-1]["sha256"] == "6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0"
    )


def test_current_media_checks_missing_wrong_bytes_and_path_escape(tmp_path: Path) -> None:
    data = b"verified-media"
    record = {
        "path": "source.mp4",
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    with pytest.raises(MediaProfileError, match="unavailable"):
        validate_current_media(tmp_path, record)
    path = tmp_path / "source.mp4"
    path.write_bytes(data)
    assert validate_current_media(tmp_path, record) == path
    path.write_bytes(b"x" * len(data))
    with pytest.raises(MediaProfileError, match="digest"):
        validate_current_media(tmp_path, record)
    with pytest.raises(MediaProfileError, match="relative"):
        validate_current_media(tmp_path, dict(record, path="../outside.mp4"))
