from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.measure import (
    _parse_vmaf_timeline,
    _read_vmaf_json,
    _vmaf_observation_score,
    measure_clip,
    probe_vmaf,
)

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"


@pytest.fixture(scope="module")
def binary() -> Path:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None and ffmpeg.is_file(), "configured real FFmpeg is required"
    assert MEDIA.is_file(), "the unchanged real decoded fixture is required"
    return ffmpeg


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _native_mean(binary: Path, video: Path, reference: Path, directory: Path) -> float:
    directory.mkdir()
    subprocess.run(
        [
            str(binary.resolve()),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(video.resolve()),
            "-i",
            str(reference.resolve()),
            "-lavfi",
            "[0:v]settb=AVTB,setpts=PTS-STARTPTS[main];"
            "[1:v]settb=AVTB,setpts=PTS-STARTPTS[ref];"
            "[main][ref]libvmaf=log_fmt=json:log_path=observations.json:"
            "pool=mean:n_subsample=1:shortest=1:repeatlast=0:eof_action=endall",
            "-f",
            "null",
            "-",
        ],
        cwd=directory,
        capture_output=True,
        check=True,
        timeout=30,
    )
    report = json.loads((directory / "observations.json").read_text(encoding="utf-8"))
    assert report["frames"]
    return float(report["pooled_metrics"]["vmaf"]["mean"])


def _variant(binary: Path, directory: Path, options: tuple[str, ...]) -> Path:
    video = directory / "variant.mp4"
    subprocess.run(
        [
            str(binary),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(MEDIA),
            "-an",
            *options,
            "-fps_mode",
            "passthrough",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "18",
            str(video),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    return video


def test_vmaf_matches_native_pooled_observations(binary: Path, tmp_path: Path) -> None:
    before = _sha(MEDIA)
    expected = _native_mean(binary, MEDIA, MEDIA, tmp_path / "native observations")
    result = probe_vmaf(MEDIA, MEDIA, binary)
    assert result is not None
    assert result.vmaf_score == round(expected, 2)
    assert result.psnr_db is None
    assert _sha(MEDIA) == before


def test_vmaf_degraded_decoded_pixels_score_below_reference(binary: Path, tmp_path: Path) -> None:
    video = _variant(binary, tmp_path, ("-vf", "drawbox=color=black:t=fill"))
    expected = _native_mean(binary, video, MEDIA, tmp_path / "damaged observations")
    original = probe_vmaf(MEDIA, MEDIA, binary)
    damaged = probe_vmaf(video, MEDIA, binary)
    assert original is not None and damaged is not None
    assert damaged.vmaf_score == round(expected, 2)
    assert damaged.vmaf_score < original.vmaf_score


def test_vmaf_accepts_matching_relative_clock(binary: Path, tmp_path: Path) -> None:
    video = _variant(binary, tmp_path, ("-vf", "setpts=PTS+3/TB"))
    expected = _native_mean(binary, video, MEDIA, tmp_path / "shifted observations")
    result = probe_vmaf(video, MEDIA, binary)
    assert result is not None
    assert result.vmaf_score == round(expected, 2)


@pytest.mark.parametrize(
    "options",
    [
        ("-t", "2"),
        ("-vf", "setpts=2*PTS"),
        ("-vf", "scale=320:180"),
        ("-pix_fmt", "yuv444p"),
    ],
    ids=["partial-reference", "wrong-clock", "wrong-geometry", "wrong-pixel-format"],
)
def test_vmaf_refuses_partial_or_incompatible_reference(
    binary: Path, tmp_path: Path, options: tuple[str, ...]
) -> None:
    reference = _variant(binary, tmp_path, options)
    before = (_sha(MEDIA), _sha(reference))
    assert probe_vmaf(MEDIA, reference, binary) is None
    assert (_sha(MEDIA), _sha(reference)) == before


@pytest.mark.parametrize("missing", ["video", "reference", "binary"])
def test_vmaf_refuses_absent_input_or_tool(binary: Path, tmp_path: Path, missing: str) -> None:
    absent = tmp_path / "absent"
    assert (
        probe_vmaf(
            absent if missing == "video" else MEDIA,
            absent if missing == "reference" else MEDIA,
            absent if missing == "binary" else binary,
        )
        is None
    )


def test_vmaf_measured_reference_runs_through_measure_clip(binary: Path) -> None:
    measured = measure_clip(MEDIA, mezzanine_path=MEDIA, ffmpeg=binary)
    assert measured.vmaf is not None
    assert measured.vmaf == probe_vmaf(MEDIA, MEDIA, binary)
    assert measured.vmaf.psnr_db is None
    assert measured.file.sha256 == _sha(MEDIA)


def _report() -> dict[str, object]:
    return {
        "version": "native-report-version",
        "frames": [
            {"frameNum": 0, "metrics": {"vmaf": 10.0}},
            {"frameNum": 1, "metrics": {"vmaf": 30.0}},
        ],
        "pooled_metrics": {"vmaf": {"min": 10.0, "max": 30.0, "mean": 20.0}},
    }


def test_vmaf_parser_preserves_observed_mean() -> None:
    assert _vmaf_observation_score(_report(), 2) == 20.0


@pytest.mark.parametrize(
    "damage",
    [
        "empty",
        "not-object",
        "version",
        "empty-version",
        "frames",
        "incomplete",
        "misindexed",
        "boolean-index",
        "frame-shape",
        "metrics-shape",
        "missing-score",
        "boolean-score",
        "string-score",
        "nonfinite-score",
        "negative-score",
        "oversized-score",
        "pooled-shape",
        "missing-mean",
        "nonfinite-mean",
        "invented-mean",
        "wrong-minimum",
    ],
)
def test_vmaf_invalid_observation_is_refused(damage: str) -> None:
    document = json.loads(json.dumps(_report()))
    if damage == "empty":
        document = {}
    elif damage == "not-object":
        document = []
    elif damage in ("version", "empty-version"):
        document["version"] = None if damage == "version" else ""
    elif damage == "frames":
        document["frames"] = None
    elif damage == "incomplete":
        document["frames"].pop()
    elif damage in ("misindexed", "boolean-index"):
        document["frames"][0]["frameNum"] = 1 if damage == "misindexed" else False
    elif damage == "frame-shape":
        document["frames"][0] = None
    elif damage == "metrics-shape":
        document["frames"][0]["metrics"] = None
    elif damage == "missing-score":
        del document["frames"][0]["metrics"]["vmaf"]
    elif damage in (
        "boolean-score",
        "string-score",
        "nonfinite-score",
        "negative-score",
        "oversized-score",
    ):
        document["frames"][0]["metrics"]["vmaf"] = {
            "boolean-score": True,
            "string-score": "10",
            "nonfinite-score": float("nan"),
            "negative-score": -1,
            "oversized-score": 101,
        }[damage]
    elif damage == "pooled-shape":
        document["pooled_metrics"] = None
    elif damage == "missing-mean":
        del document["pooled_metrics"]["vmaf"]["mean"]
    elif damage in ("nonfinite-mean", "invented-mean", "wrong-minimum"):
        field, value = {
            "nonfinite-mean": ("mean", float("inf")),
            "invented-mean": ("mean", 95.0),
            "wrong-minimum": ("min", 9.0),
        }[damage]
        document["pooled_metrics"]["vmaf"][field] = value
    with pytest.raises(ValueError):
        _vmaf_observation_score(document, 2)


def _timeline() -> dict[str, object]:
    return {
        "frames": [
            {
                "best_effort_timestamp_time": "3.000000",
                "duration_time": "0.040000",
                "width": 640,
                "height": 360,
                "pix_fmt": "yuv420p",
            },
            {
                "best_effort_timestamp_time": "3.040000",
                "duration_time": "0.040000",
                "width": 640,
                "height": 360,
                "pix_fmt": "yuv420p",
            },
        ]
    }


def test_vmaf_timeline_uses_relative_observed_clocks() -> None:
    shifted = json.loads(json.dumps(_timeline()))
    shifted["frames"][0]["best_effort_timestamp_time"] = "0.000000"
    shifted["frames"][1]["best_effort_timestamp_time"] = "0.040000"
    assert _parse_vmaf_timeline(shifted) == _parse_vmaf_timeline(_timeline())


@pytest.mark.parametrize(
    "damage",
    [
        "empty",
        "not-object",
        "frames",
        "frame-shape",
        "timestamp",
        "nonfinite-time",
        "zero-denominator",
        "duration",
        "negative-duration",
        "repeated-clock",
        "width",
        "height",
        "pixel-format",
    ],
)
def test_vmaf_invalid_timeline_is_refused(damage: str) -> None:
    document = json.loads(json.dumps(_timeline()))
    if damage == "empty":
        document["frames"] = []
    elif damage == "not-object":
        document = []
    elif damage == "frames":
        document["frames"] = None
    elif damage == "frame-shape":
        document["frames"][0] = 1
    elif damage in (
        "timestamp",
        "nonfinite-time",
        "zero-denominator",
        "duration",
        "negative-duration",
        "width",
        "height",
        "pixel-format",
    ):
        field, value = {
            "timestamp": ("best_effort_timestamp_time", None),
            "nonfinite-time": ("best_effort_timestamp_time", "NaN"),
            "zero-denominator": ("best_effort_timestamp_time", "1/0"),
            "duration": ("duration_time", None),
            "negative-duration": ("duration_time", "-1"),
            "width": ("width", True),
            "height": ("height", 0),
            "pixel-format": ("pix_fmt", ""),
        }[damage]
        document["frames"][0][field] = value
    elif damage == "repeated-clock":
        document["frames"][1]["best_effort_timestamp_time"] = "3.000000"
    with pytest.raises(ValueError):
        _parse_vmaf_timeline(document)


@pytest.mark.parametrize("payload", [b"{}{}", b'{"mean":1,"mean":2}', b'{"mean":NaN}', b"\xff"])
def test_vmaf_raw_json_refuses_ambiguous_or_malformed_bytes(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "report.json"
    path.write_bytes(payload)
    with pytest.raises(ValueError):
        _read_vmaf_json(path, limit=1024)


def test_vmaf_raw_json_enforces_read_bound(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_bytes(b"{} ")
    with pytest.raises(ValueError):
        _read_vmaf_json(path, limit=2)


def test_vmaf_refuses_truncated_real_media(binary: Path, tmp_path: Path) -> None:
    damaged = tmp_path / "truncated.mp4"
    encoded = MEDIA.read_bytes()
    damaged.write_bytes(encoded[: len(encoded) // 2])
    before = _sha(damaged)
    assert probe_vmaf(damaged, MEDIA, binary) is None
    assert _sha(damaged) == before
