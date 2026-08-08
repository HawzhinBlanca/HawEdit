"""A delivered clip appears as one complete, write-once directory."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from hawedit.artifact_bundle import ArtifactBundle, BundleAlreadyExists, BundleError

SUFFIXES = ("ass", "mp4", "srt", "edl", "json")


def stage_complete(bundle: ArtifactBundle, marker: str = "one") -> None:
    for suffix in SUFFIXES:
        if suffix == "mp4":
            bundle.staged_path(suffix).write_bytes(f"{marker}-{suffix}".encode())
        else:
            bundle.write_text(suffix, f"{marker}-{suffix}")


def test_a_bundle_is_invisible_until_the_exact_set_is_published(tmp_path: Path) -> None:
    bundle = ArtifactBundle.create(tmp_path, "episode-s0-1")
    stage_complete(bundle)

    assert not bundle.final_dir.exists()
    published = bundle.publish()

    assert published == bundle.final_paths
    assert all(path.is_file() and path.stat().st_size > 0 for path in published)
    assert not bundle.staging_dir.exists()


@pytest.mark.parametrize("missing", SUFFIXES)
def test_publication_refuses_any_missing_artifact(tmp_path: Path, missing: str) -> None:
    bundle = ArtifactBundle.create(tmp_path, f"missing-{missing}")
    stage_complete(bundle)
    bundle.staged_path(missing).unlink()

    with pytest.raises(BundleError, match="missing"):
        bundle.publish()
    assert not bundle.final_dir.exists()


def test_publication_refuses_empty_or_unexpected_content(tmp_path: Path) -> None:
    empty = ArtifactBundle.create(tmp_path, "empty")
    stage_complete(empty)
    empty.staged_path("edl").write_bytes(b"")
    with pytest.raises(BundleError, match="empty"):
        empty.publish()

    extra = ArtifactBundle.create(tmp_path, "extra")
    stage_complete(extra)
    (extra.staging_dir / "plausible.mov").write_bytes(b"not part of the contract")
    with pytest.raises(BundleError, match="extra"):
        extra.publish()


def test_a_completed_bundle_is_write_once(tmp_path: Path) -> None:
    winner = ArtifactBundle.create(tmp_path, "same")
    stage_complete(winner, "winner")
    winner.publish()

    with pytest.raises(BundleAlreadyExists, match="overwrite"):
        ArtifactBundle.create(tmp_path, "same")
    assert winner.final_path("mp4").read_bytes() == b"winner-mp4"


def test_a_staging_directory_creation_failure_is_a_domain_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    def fail_mkdtemp(*args: object, **kwargs: object) -> str:
        raise OSError("volume is read-only")

    monkeypatch.setattr(tempfile, "mkdtemp", fail_mkdtemp)
    with pytest.raises(BundleError, match="read-only"):
        ArtifactBundle.create(tmp_path, "unwritable")
    assert not (tmp_path / "unwritable").exists()


def test_two_workers_publish_one_whole_winner_never_a_mixed_set(tmp_path: Path) -> None:
    first = ArtifactBundle.create(tmp_path, "race")
    second = ArtifactBundle.create(tmp_path, "race")
    stage_complete(first, "first")
    stage_complete(second, "second")
    barrier = Barrier(2)

    def publish(bundle: ArtifactBundle) -> str:
        barrier.wait()
        try:
            bundle.publish()
            return "published"
        except BundleAlreadyExists:
            bundle.discard()
            return "refused"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(publish, (first, second)))

    assert sorted(outcomes) == ["published", "refused"]
    payloads = {path.read_bytes().split(b"-", 1)[0] for path in first.final_paths}
    assert payloads in ({b"first"}, {b"second"})


def test_a_crashed_private_bundle_does_not_block_a_clean_retry(tmp_path: Path) -> None:
    crashed = ArtifactBundle.create(tmp_path, "retry")
    crashed.write_text("ass", "partial private work")

    retry = ArtifactBundle.create(tmp_path, "retry")
    stage_complete(retry, "retry")
    retry.publish()

    assert retry.final_dir.is_dir()
    assert crashed.staging_dir.is_dir()
    crashed.discard()
    assert not crashed.staging_dir.exists()


def test_cleanup_refuses_to_recurse_into_unexpected_content(tmp_path: Path) -> None:
    bundle = ArtifactBundle.create(tmp_path, "unexpected")
    unexpected = bundle.staging_dir / "directory"
    unexpected.mkdir()

    with pytest.raises(BundleError, match="refusing to recursively remove"):
        bundle.discard()
    assert unexpected.is_dir()


@pytest.mark.parametrize(
    "unsafe", ["../escape", "a/b", "a\\b", "CON", "clip:one", " trailing", "trailing "]
)
def test_bundle_ids_are_cross_platform_path_safe(tmp_path: Path, unsafe: str) -> None:
    with pytest.raises(ValueError, match="media_id"):
        ArtifactBundle.create(tmp_path, unsafe)
