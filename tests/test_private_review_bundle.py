"""Private candidate storage, independent of media or publication authorization."""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.artifact_bundle import ArtifactBundle, BundleError
from hawedit.studio_private import PrivateDirectory
from studio_test_storage import seed_private_file


def test_private_review_bundle_is_owner_private_before_and_after_atomic_freeze(
    tmp_path: Path,
) -> None:
    bundle = ArtifactBundle.create(tmp_path / "review", "c-1", private=True)
    PrivateDirectory(bundle.staging_dir, create=False)
    for path in bundle.staging_paths:
        seed_private_file(path, b"diagnostic packaging, not delivered media")
    paths = bundle.publish()
    assert len(paths) == 7
    published = PrivateDirectory(bundle.final_dir, create=False)
    for path in paths:
        published.check_file(path.name)
    assert not bundle.staging_dir.exists()


def test_private_review_bundle_refuses_existing_unsafe_root_without_repair(
    tmp_path: Path,
) -> None:
    root = tmp_path / "existing"
    root.mkdir(mode=0o755)
    sentinel = root / "sentinel.txt"
    sentinel.write_bytes(b"owner data")
    before = root.stat().st_mode
    with pytest.raises(BundleError, match="private|unsafe|nonprivate|unavailable"):
        ArtifactBundle.create(root, "c-1", private=True)
    assert root.stat().st_mode == before
    assert sentinel.read_bytes() == b"owner data"
    assert {p.name for p in root.iterdir()} == {"sentinel.txt"}
