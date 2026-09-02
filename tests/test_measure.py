from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.measure import (
    ClipMeasurement,
    MeasureError,
    main,
    measure_clip,
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
