from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.measure import (
    ClipMeasurement,
    MeasureError,
    detect_caption_ink_in_band,
    main,
    measure_caption_events_contrast,
    measure_clip,
    probe_caption_ink,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_VIDEO = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"


def test_measure_reads_only_the_delivered_file() -> None:
    """AST-level isolation test: hawedit.measure must never import render or pipeline."""
    measure_py = ROOT / "src" / "hawedit" / "measure.py"
    assert measure_py.is_file(), "measure.py must exist"

    tree = ast.parse(measure_py.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    forbidden = {"hawedit.render", "hawedit.pipeline", "render", "pipeline"}
    found_forbidden = imported_modules.intersection(forbidden)
    assert not found_forbidden, (
        f"hawedit.measure imports forbidden render/pipeline modules: {found_forbidden}"
    )


def test_measure_refuses_missing_file() -> None:
    non_existent = ROOT / "non_existent_file.mp4"
    with pytest.raises(MeasureError, match="does not exist|not found"):
        measure_clip(non_existent)


def test_measure_probes_container_and_streams_accurately() -> None:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None or not ffmpeg.is_file():
        pytest.skip("needs ffmpeg/ffprobe")
    if not FIXTURE_VIDEO.is_file():
        pytest.skip("needs fixture video")

    measurement = measure_clip(FIXTURE_VIDEO)
    assert isinstance(measurement, ClipMeasurement)
    assert measurement.schema == 1
    assert measurement.file.size_bytes > 0
    assert len(measurement.file.sha256) == 64
    assert measurement.video.width == 640
    assert measurement.video.height == 360
    assert measurement.video.fps > 0
    assert measurement.video.duration_ms > 0
    assert measurement.audio.channels >= 1
    assert measurement.audio.sample_rate > 0


def test_measure_ebur128_loudness_and_silences() -> None:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None or not ffmpeg.is_file():
        pytest.skip("needs ffmpeg")
    if not FIXTURE_VIDEO.is_file():
        pytest.skip("needs fixture video")

    measurement = measure_clip(FIXTURE_VIDEO)
    assert measurement.audio.integrated_lufs < 0
    assert measurement.audio.true_peak_db <= 10.0
    assert isinstance(measurement.audio.silences, list)


def test_measure_scene_cuts() -> None:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None or not ffmpeg.is_file():
        pytest.skip("needs ffmpeg")
    if not FIXTURE_VIDEO.is_file():
        pytest.skip("needs fixture video")

    measurement = measure_clip(FIXTURE_VIDEO)
    assert "cuts_ms" in measurement.scenes
    assert isinstance(measurement.scenes["cuts_ms"], list)


def test_measure_cli_emits_valid_json(tmp_path: Path) -> None:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None or not ffmpeg.is_file():
        pytest.skip("needs ffmpeg")
    if not FIXTURE_VIDEO.is_file():
        pytest.skip("needs fixture video")

    out_json = tmp_path / "measured.json"
    exit_code = main([str(FIXTURE_VIDEO), "--out", str(out_json)])
    assert exit_code == 0
    assert out_json.is_file()

    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["schema"] == 1
    assert data["video"]["width"] == 640
    assert data["video"]["height"] == 360


def test_measure_caption_events_contrast_evaluates_video_background(tmp_path: Path) -> None:
    if not FIXTURE_VIDEO.is_file():
        pytest.skip("needs fixture video")

    ass_text = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.50,0:00:01.50,Kurdish,,0,0,0,,دەقی یەکەم
Dialogue: 0,0:00:02.00,0:00:03.00,Kurdish,,0,0,0,,دەقی دووەم
"""
    ass_path = tmp_path / "test.ass"
    ass_path.write_text(ass_text, encoding="utf-8")

    records = measure_caption_events_contrast(FIXTURE_VIDEO, ass_path)
    assert len(records) == 2

    for start_ms, end_ms, cr, needs_plate in records:
        assert isinstance(start_ms, int)
        assert isinstance(end_ms, int)
        assert end_ms > start_ms
        assert isinstance(cr, float)
        assert cr >= 1.0
        assert isinstance(needs_plate, bool)


def test_textured_background_cannot_prove_caption_presence(tmp_path: Path) -> None:
    """AC-05: An uncaptioned textured video must not be accepted as burned-in captions."""
    import cv2
    import numpy as np

    # 1. Synthetic video with high Laplacian variance (textured noise) but NO captions
    h, w = 1920, 1080
    np.random.seed(42)
    video_path = tmp_path / "textured_uncaptioned.mp4"
    fourcc = cv2.VideoWriter.fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 10.0, (w, h))

    for _ in range(10):
        frame = np.random.randint(60, 180, (h, w, 3), dtype=np.uint8)
        for y in range(0, h, 30):
            frame[y : y + 15, :] = np.clip(frame[y : y + 15, :].astype(int) + 40, 0, 255)
        out.write(frame)
    out.release()

    ass_text = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.20,0:00:00.80,Kurdish,,0,0,0,,سڵاو ئەمە تاقیکردنەوەیە
"""
    ass_path = tmp_path / "cues.ass"
    ass_path.write_text(ass_text, encoding="utf-8")

    # Background texture must NOT be accepted as proof of burned-in captions
    meas = probe_caption_ink(video_path, ass_path)
    assert meas.events_count == 1
    assert meas.ink_energy_detected_share == 0.0

    # Test single-frame probe directly
    sample_frame = np.random.randint(60, 180, (h, w, 3), dtype=np.uint8)
    for y in range(0, h, 30):
        sample_frame[y : y + 15, :] = np.clip(sample_frame[y : y + 15, :].astype(int) + 40, 0, 255)
    has_ink, _ = detect_caption_ink_in_band(sample_frame, int(h * 0.65), int(h * 0.95))
    assert has_ink is False


def test_missing_visual_measurement_dependency_never_reports_success(tmp_path: Path) -> None:
    """VE-00 / F01: Missing measurement dependency must raise MeasureError and never
    fabricate success.
    """
    import sys
    from unittest.mock import patch

    import numpy as np

    fake_video = tmp_path / "fake.mp4"
    fake_video.write_bytes(b"dummy video")
    fake_ass = tmp_path / "fake.ass"
    fake_ass.write_text(
        "[Script Info]\nPlayResX: 1080\nPlayResY: 1920\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,تست\n",
        encoding="utf-8",
    )
    frame = np.zeros((1920, 1080, 3), dtype=np.uint8)

    with patch.dict(sys.modules, {"cv2": None}):
        with pytest.raises(MeasureError, match="OpenCV.*required"):
            probe_caption_ink(fake_video, fake_ass)

        with pytest.raises(MeasureError, match="OpenCV.*required"):
            detect_caption_ink_in_band(frame, 1000, 1800)

        with pytest.raises(MeasureError, match="OpenCV.*required"):
            measure_caption_events_contrast(fake_video, fake_ass)


def test_measured_carries_speaking_face_share(tmp_path: Path) -> None:
    from hawedit.measure import (
        AudioMeasurement,
        CaptionMeasurement,
        ClipMeasurement,
        FaceTrackMeasurement,
        FileSummary,
        VideoMeasurement,
    )

    faces = FaceTrackMeasurement(
        sample_interval_ms=200,
        samples_count=10,
        face_detected_frames_count=10,
        face_detected_share=1.0,
        median_face_height_share=0.25,
        median_y_center_share=0.38,
        first_frame_face_share=0.25,
        speaking_samples_count=8,
        speaking_face_frames_count=8,
        speaking_face_share=1.0,
    )
    meas = ClipMeasurement(
        schema=1,
        file=FileSummary(path=str(tmp_path / "clip.mp4"), sha256="a" * 64, size_bytes=1234),
        video=VideoMeasurement(
            width=1080,
            height=1920,
            fps=25.0,
            fps_ratio="25/1",
            duration_ms=2000,
            frames_count=50,
            bitrate_kbps=4000,
            codec="h264",
            pix_fmt="yuv420p",
            color_space=None,
            color_transfer=None,
            color_primaries=None,
        ),
        audio=AudioMeasurement(
            codec="aac",
            sample_rate=48000,
            channels=2,
            duration_ms=2000,
            integrated_lufs=-14.0,
            true_peak_db=-1.0,
            lra_lu=2.0,
            silences=[],
            total_silence_ms=0,
            silence_share=0.0,
        ),
        scenes={"cuts_ms": []},
        faces=faces,
        captions=CaptionMeasurement(
            events_count=1,
            ink_energy_detected_share=1.0,
            median_contrast_ratio=4.5,
        ),
        vmaf=None,
        tool_metadata={},
    )
    payload = meas.to_dict()
    assert "speaking_face_share" in payload["faces"]
    assert payload["faces"]["speaking_face_share"] == 1.0
    assert payload["faces"]["speaking_samples_count"] == 8
    assert payload["faces"]["speaking_face_frames_count"] == 8

    # Test roundtrip
    restored = ClipMeasurement.from_dict(payload)
    assert restored.faces.speaking_face_share == 1.0
    assert restored.faces.speaking_samples_count == 8
