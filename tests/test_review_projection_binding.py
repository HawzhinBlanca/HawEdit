"""Real decoded-media file binding, not editor or publication acceptance."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from hawedit.measure import measure_clip
from hawedit.studio_artifacts import open_preview
from hawedit.studio_generation import project_generation_result

MEDIA = Path(__file__).parent / "fixtures" / "kurdish-speech-3cuts.mp4"


@pytest.fixture(scope="module")
def measured_source(tmp_path_factory: pytest.TempPathFactory) -> tuple[bytes, str]:
    folder = tmp_path_factory.mktemp("review-projection-source")
    media = folder / "source.mp4"
    shutil.copyfile(MEDIA, media)
    return media.read_bytes(), measure_clip(media).to_json()


@pytest.fixture
def candidate(tmp_path: Path, measured_source: tuple[bytes, str]) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "job-one"
    directory = root / "review" / "clip-one"
    directory.mkdir(parents=True)
    media, measurement = measured_source
    (directory / "clip-one.mp4").write_bytes(media)
    (directory / "clip-one.measured.json").write_text(measurement, encoding="utf-8")
    report = {
        "render": {"path": str(directory / "clip-one.mp4")},
        "clip": {"clip_id": "clip-one", "output": {"title_ckb": "Review"}},
        "episode_manifest": {"clips": [{"clip_id": "clip-one", "delivery_dir": "review/clip-one"}]},
    }
    (root / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return root, report


def assert_refused(root: Path, report: dict[str, Any]) -> None:
    result = project_generation_result(report, root)
    assert result["status"] == "failed"
    assert result["publication_verified"] is False and result["published_count"] == 0
    view = result["clips"][0]
    assert view["state"] == "failed" and view["error"]
    assert view["sha256"] is None and view["duration_s"] is None
    assert view["artifact_path"] is None


@pytest.mark.parametrize("suffix", ["mp4", "measured.json"])
def test_review_projection_refuses_hardlinked_evidence(
    candidate: tuple[Path, dict[str, Any]], suffix: str
) -> None:
    root, report = candidate
    artifact = root / "review" / "clip-one" / f"clip-one.{suffix}"
    original = artifact.read_bytes()
    alias = root / f"retained-{suffix}"
    os.link(artifact, alias)
    assert artifact.stat().st_nlink == 2
    assert_refused(root, report)
    assert artifact.read_bytes() == alias.read_bytes() == original


@pytest.mark.parametrize("damage", ["directory", "basename"])
def test_review_projection_requires_exact_private_candidate_scope(
    candidate: tuple[Path, dict[str, Any]], damage: str
) -> None:
    root, report = candidate
    # Exercise the single-render caller independently of the episode branch.
    report.pop("episode_manifest")
    directory = root / "review" / "clip-one"
    if damage == "directory":
        directory.rename(root / "review" / "another-clip")
        report["render"]["path"] = str(root / "review" / "another-clip" / "clip-one.mp4")
    else:
        (directory / "clip-one.mp4").rename(directory / "another-clip.mp4")
        report["render"]["path"] = str(directory / "another-clip.mp4")
    assert_refused(root, report)


@pytest.mark.parametrize("damage", ["schema-bool", "size-float", "duplicate-key", "nonfinite"])
def test_review_projection_requires_preview_measurement_contract(
    candidate: tuple[Path, dict[str, Any]], damage: str
) -> None:
    root, report = candidate
    path = root / "review" / "clip-one" / "clip-one.measured.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if damage == "schema-bool":
        document["schema"] = True
    elif damage == "size-float":
        document["file"]["size_bytes"] = float(document["file"]["size_bytes"])
    elif damage == "nonfinite":
        document["video"]["fps"] = float("nan")
    text = json.dumps(document)
    if damage == "duplicate-key":
        text = '{"schema":99,' + text[1:]
    path.write_text(text, encoding="utf-8")
    assert_refused(root, report)


def test_review_projection_matches_real_preview_evidence(
    candidate: tuple[Path, dict[str, Any]],
) -> None:
    root, report = candidate
    result = project_generation_result(report, root)
    assert result["status"] == "awaiting-review" and result["publication_verified"] is False
    view = result["clips"][0]
    with open_preview(root.parent, root.name, "clip-one") as preview:
        assert view["sha256"] == preview.sha256
        assert view["duration_s"] == preview.duration_ms / 1000
        assert len(preview.stream.read()) == preview.size
    assert view["artifact_path"] == "review/clip-one/clip-one.mp4"


def test_review_projection_reopens_measurement_after_real_media_read(
    candidate: tuple[Path, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, report = candidate
    directory = root / "review" / "clip-one"
    path = directory / "clip-one.measured.json"
    payload = (directory / "clip-one.mp4").read_bytes()
    original = path.stat()
    document = json.loads(path.read_text(encoding="utf-8"))
    document["video"]["duration_ms"] += 1
    changed = json.dumps(document, indent=2)
    assert len(changed.replace("\n", os.linesep).encode("utf-8")) == original.st_size
    real_sha256 = hashlib.sha256
    observations: list[int] = []

    class ObservedHash:
        def __init__(self, data: bytes = b"") -> None:
            self.real = real_sha256(data)

        def update(self, data: bytes) -> None:
            self.real.update(data)
            if data == payload and not observations:
                observations.append(len(data))
                # Real file damage with the original size/mtime, not a forged hash result.
                path.write_text(changed, encoding="utf-8")
                os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))

        def hexdigest(self) -> str:
            return self.real.hexdigest()

    monkeypatch.setattr(hashlib, "sha256", ObservedHash)
    assert_refused(root, report)
    assert observations == [len(payload)]
