"""Real private preview recovery integrity, not editorial/publication acceptance."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

import hawedit.pipeline as pipeline_module
import test_pipeline as pipeline_fixtures
from hawedit.captions import find_ffmpeg
from hawedit.pipeline import PipelineRun, StageSkipped, run_pipeline
from hawedit.render import RenderResult, render_clip
from studio_test_storage import make_private_directory, seed_private_file


def _run(work: Path, **overrides: Any) -> PipelineRun:
    return run_pipeline(
        pipeline_fixtures.FIXTURE,
        work,
        media_id="cache-integrity",
        transcript=pipeline_fixtures.a_transcript("cache-integrity"),
        select_sentences=(0,),
        qc=pipeline_fixtures._test_qc(
            False, reviewed_sha256=pipeline_fixtures.FIXTURE_RENDER_S0_SHA256
        ),
        verdict=pipeline_fixtures.a_verdict(100, 1700),
        **overrides,
    )


@pytest.fixture(scope="module")
def original(tmp_path_factory: pytest.TempPathFactory) -> PipelineRun:
    assert find_ffmpeg() is not None, "Actual decoded-media recovery requires FFmpeg"
    run = _run(tmp_path_factory.mktemp("real-cache-render") / "work")
    assert run.render is not None and not isinstance(run.render, StageSkipped), run.render
    assert run.clip is not None and not isinstance(run.clip, StageSkipped)
    assert isinstance(run.delivery, StageSkipped)
    return run


@pytest.fixture
def candidate(original: PipelineRun, tmp_path: Path) -> tuple[Path, Path]:
    assert original.render is not None and not isinstance(original.render, StageSkipped)
    packet = Path(original.render.path).parent
    old_work = packet.parent.parent
    work = tmp_path / "work"
    shutil.copytree(old_work, work, ignore=shutil.ignore_patterns("review"))
    review = work / "review"
    make_private_directory(review)
    copy = review / packet.name
    make_private_directory(copy)
    for member in packet.iterdir():
        seed_private_file(copy / member.name, member.read_bytes())
    return work, copy


def _bytes(packet: Path) -> dict[str, bytes]:
    return {member.name: member.read_bytes() for member in packet.iterdir()}


def _assert_refused(work: Path, packet: Path) -> PipelineRun:
    before = _bytes(packet)
    run = _run(work)
    assert isinstance(run.render, StageSkipped), run.render
    assert "existing private candidate" in run.render.reason
    assert isinstance(run.delivery, StageSkipped)
    assert "existing private candidate" in run.delivery.reason
    assert not run.complete
    assert _bytes(packet) == before, "Refusal must not rewrite or discard prior evidence"
    assert not (work / packet.name).exists(), "Private refusal must not publish"
    return run


def test_private_cache_refuses_changed_mp4_without_overwriting(
    candidate: tuple[Path, Path],
) -> None:
    work, packet = candidate
    mp4 = packet / f"{packet.name}.mp4"
    assert mp4.read_bytes() != pipeline_fixtures.FIXTURE.read_bytes()
    shutil.copyfile(pipeline_fixtures.FIXTURE, mp4)
    _assert_refused(work, packet)


@pytest.mark.parametrize(
    "suffix", ["mp4", "ass", "srt", "edl", "json", "measured.json", "edit_plan.json"]
)
def test_private_cache_refuses_missing_member_without_overwriting(
    candidate: tuple[Path, Path], suffix: str, tmp_path: Path
) -> None:
    work, packet = candidate
    (packet / f"{packet.name}.{suffix}").rename(tmp_path / f"preserved.{suffix}")
    _assert_refused(work, packet)


@pytest.mark.parametrize(
    "damage",
    ["malformed", "duplicate", "nonfinite", "extra", "width", "duration", "sha", "size", "tool"],
)
def test_private_cache_refuses_invalid_measurement(
    candidate: tuple[Path, Path], damage: str
) -> None:
    work, packet = candidate
    path = packet / f"{packet.name}.measured.json"
    value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if damage == "malformed":
        path.write_text("not json", encoding="utf-8")
    elif damage == "duplicate":
        path.write_text('{"schema":1,"schema":1}', encoding="utf-8")
    elif damage == "nonfinite":
        value["audio"]["integrated_lufs"] = float("nan")
        path.write_text(json.dumps(value), encoding="utf-8")
    else:
        if damage == "extra":
            value["unmeasured_claim"] = True
        elif damage == "width":
            value["video"]["width"] += 100
        elif damage == "duration":
            value["video"]["duration_ms"] += 100
        elif damage == "sha":
            value["file"]["sha256"] = "0" * 64
        elif damage == "size":
            value["file"]["size_bytes"] += 1
        elif damage == "tool":
            value["tool_metadata"]["ffmpeg_version"] = "fabricated"
        path.write_text(json.dumps(value), encoding="utf-8")
    _assert_refused(work, packet)


@pytest.mark.parametrize(
    "block,value", [("audio", None), ("audio", 4), ("faces", 4), ("captions", None)]
)
def test_private_cache_refuses_malformed_measurement_blocks(
    candidate: tuple[Path, Path], block: str, value: object
) -> None:
    work, packet = candidate
    path = packet / f"{packet.name}.measured.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document[block] = value
    path.write_text(json.dumps(document), encoding="utf-8")
    _assert_refused(work, packet)


@pytest.mark.parametrize("suffix", ["json", "edit_plan.json"])
@pytest.mark.parametrize("field", ["clip_id", "media_id", "media_sha256", "interval"])
def test_private_cache_refuses_mismatched_packet_binding(
    candidate: tuple[Path, Path], suffix: str, field: str
) -> None:
    work, packet = candidate
    path = packet / f"{packet.name}.{suffix}"
    value = json.loads(path.read_text(encoding="utf-8"))
    if field == "interval":
        if suffix == "json":
            value["out_ms"] += 100
        else:
            value["time_mapping"]["clip_out_ms"] += 100
    else:
        value[field] = "0" * 64 if field == "media_sha256" else "foreign"
    path.write_text(json.dumps(value), encoding="utf-8")
    _assert_refused(work, packet)


def test_private_cache_refuses_hardlinked_member(
    candidate: tuple[Path, Path], tmp_path: Path
) -> None:
    work, packet = candidate
    path = packet / f"{packet.name}.mp4"
    alias = tmp_path / "shared.mp4"
    os.link(path, alias)
    assert path.stat().st_nlink == 2
    _assert_refused(work, packet)
    assert alias.read_bytes() == path.read_bytes()


def test_private_cache_reuses_unchanged_real_media_without_rewriting(
    candidate: tuple[Path, Path], original: PipelineRun
) -> None:
    work, packet = candidate
    before = _bytes(packet)
    repeated = _run(work)
    assert repeated.render is not None and not isinstance(repeated.render, StageSkipped)
    assert original.render is not None and not isinstance(original.render, StageSkipped)
    assert Path(repeated.render.path) == packet / f"{packet.name}.mp4"
    assert repeated.render.width == original.render.width
    assert repeated.render.height == original.render.height
    assert repeated.render.measured_duration_ms == original.render.measured_duration_ms
    assert isinstance(repeated.delivery, StageSkipped)
    assert repeated.delivery.reason == "awaiting human review"
    assert not repeated.complete
    assert _bytes(packet) == before
    assert not (work / packet.name).exists()


@pytest.mark.parametrize(
    "options",
    [
        {"hook_banner": True, "hook_text": "A different headline"},
        {"keyword_emphasis": False},
        {"caption_style": "viral_popup"},
        {"silence_threshold_ms": 250},
        {"eased_push": True},
        {"music_ducking_volume": 0.1},
    ],
)
def test_private_cache_refuses_changed_render_controls(
    candidate: tuple[Path, Path], options: dict[str, Any]
) -> None:
    work, packet = candidate
    before = _bytes(packet)
    run = _run(work, **options)
    assert isinstance(run.render, StageSkipped), "Changed settings reused the old MP4"
    assert "existing private candidate" in run.render.reason
    assert "render request" in run.render.reason
    assert isinstance(run.delivery, StageSkipped)
    assert not run.complete
    assert _bytes(packet) == before


@pytest.mark.parametrize("binding", [None, "0" * 64])
def test_private_cache_refuses_missing_or_changed_request_binding(
    candidate: tuple[Path, Path], binding: str | None
) -> None:
    work, packet = candidate
    path = packet / f"{packet.name}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if binding is None:
        value["provenance"].pop("render_request_sha256", None)
    else:
        value["provenance"]["render_request_sha256"] = binding
    path.write_text(json.dumps(value), encoding="utf-8")
    _assert_refused(work, packet)


def _pixels(video: Path) -> bytes:
    binary = find_ffmpeg()
    assert binary is not None
    decoded = subprocess.run(
        [
            str(binary),
            "-v",
            "error",
            "-ss",
            "0.3",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "scale=160:284",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        capture_output=True,
        timeout=30,
        check=True,
    )
    assert len(decoded.stdout) == 160 * 284 * 3
    assert len(set(decoded.stdout)) > 1
    return decoded.stdout


def test_headline_revision_changes_decoded_pixels_and_preserves_original(tmp_path: Path) -> None:
    first = _run(tmp_path / "first", hook_banner=True, hook_text="Original headline")
    assert first.render is not None and not isinstance(first.render, StageSkipped), first.render
    assert first.clip is not None and not isinstance(first.clip, StageSkipped)
    packet = Path(first.render.path).parent
    before = _bytes(packet)
    original_transcripts = _bytes(tmp_path / "first" / "transcripts")
    revision = _run(tmp_path / "revision", hook_banner=True, hook_text="Revised headline")
    assert revision.render is not None and not isinstance(revision.render, StageSkipped), (
        revision.render
    )
    assert revision.clip is not None and not isinstance(revision.clip, StageSkipped)
    assert first.clip.transcript == revision.clip.transcript
    assert _pixels(Path(first.render.path)) != _pixels(Path(revision.render.path))
    assert _bytes(packet) == before
    assert _bytes(tmp_path / "first" / "transcripts") == original_transcripts
    assert isinstance(revision.delivery, StageSkipped)
    assert not revision.complete


def test_pipeline_refuses_asset_changed_after_real_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fonts = tmp_path / "fonts"
    shutil.copytree(pipeline_module.FONTS_DIR, fonts)
    monkeypatch.setattr(pipeline_module, "FONTS_DIR", fonts)
    actual_render = render_clip

    def render_then_change_assets(*args: Any, **kwargs: Any) -> RenderResult:
        rendered = actual_render(*args, **kwargs)
        (fonts / "OFL.txt").write_bytes(b"changed after actual native encode")
        return rendered

    # Fault injection delegates to the real renderer; no output or measurement is mocked.
    monkeypatch.setattr(pipeline_module, "render_clip", render_then_change_assets)
    work = tmp_path / "work"
    result = _run(work)
    assert isinstance(result.render, StageSkipped)
    assert "render request changed during native rendering" in result.render.reason
    assert not result.complete
    assert not (work / "review" / "cache-integrity-s0-0").exists()
