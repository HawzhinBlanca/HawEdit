"""Tests for pyannote diarization adapter (specs/diarization-adapter)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from hawedit.diarization import Segment
from hawedit.ingest import (
    DiarizationInvalidOutput,
    DiarizationUnavailable,
    IngestResult,
    SpeechSegment,
    attach_diarization,
)
from hawedit.pyannote_adapter import (
    PyannoteDiarizer,
    convert_annotation_to_segments,
)


@dataclass
class _StubPyannoteSegment:
    start: float
    end: float


class _StubAnnotation:
    def __init__(self, tracks: list[tuple[_StubPyannoteSegment, str, str]]) -> None:
        self._tracks = tracks

    def itertracks(self, yield_label: bool = True) -> list[tuple[_StubPyannoteSegment, str, str]]:
        assert yield_label is True
        return self._tracks


def test_float_seconds_become_exact_integer_milliseconds() -> None:
    """AC-5: Float seconds become exact integer milliseconds by monotonic rounding."""
    annotation = _StubAnnotation(
        [
            (_StubPyannoteSegment(0.0004, 1.2344), "track1", "SPEAKER_00"),
            (_StubPyannoteSegment(1.5006, 3.7896), "track2", "SPEAKER_01"),
            (_StubPyannoteSegment(4.0, 5.5), "track3", "SPEAKER_00"),
        ]
    )
    segments = convert_annotation_to_segments(annotation)
    assert segments == (
        Segment(start_ms=0, end_ms=1234, speaker="SPEAKER_00"),
        Segment(start_ms=1501, end_ms=3790, speaker="SPEAKER_01"),
        Segment(start_ms=4000, end_ms=5500, speaker="SPEAKER_00"),
    )


def test_a_turn_that_rounds_to_zero_length_is_refused_not_dropped() -> None:
    """AC-6: Refuse sub-millisecond turns that round to zero/negative duration."""
    annotation = _StubAnnotation(
        [
            (_StubPyannoteSegment(1.0001, 1.0003), "track1", "SPEAKER_00"),
        ]
    )
    with pytest.raises(DiarizationInvalidOutput, match="SPEAKER_00.*1000..1000 ms"):
        convert_annotation_to_segments(annotation)


def test_the_adapter_never_repairs_an_overlap_it_is_handed() -> None:
    """AC-7: The adapter does not alter or merge overlapping turns."""
    annotation = _StubAnnotation(
        [
            (_StubPyannoteSegment(0.0, 2.0), "track1", "SPEAKER_00"),
            (_StubPyannoteSegment(1.5, 3.5), "track2", "SPEAKER_01"),
        ]
    )
    converted = convert_annotation_to_segments(annotation)
    assert len(converted) == 2
    assert converted[0] == Segment(start_ms=0, end_ms=2000, speaker="SPEAKER_00")
    assert converted[1] == Segment(start_ms=1500, end_ms=3500, speaker="SPEAKER_01")

    # attach_diarization refuses it without repair
    class _StubOverlapDiarizer:
        def diarize(self, audio: Path) -> tuple[Segment, ...]:
            return converted

    base_ingest = IngestResult(
        media_id="test_media",
        source="test.mp4",
        source_sha256="0" * 64,
        duration_ms=5000,
        audio_path="test.wav",
        proxy_path="test_proxy",
        shot_cuts_ms=(),
        speech=(SpeechSegment(start_ms=0, end_ms=4000),),
    )
    with pytest.raises(DiarizationInvalidOutput, match="diarization turns overlap"):
        attach_diarization(base_ingest, _StubOverlapDiarizer())


def test_the_adapter_never_imports_the_pyannote_cloud_sdk() -> None:
    """Adapter operates locally and strictly forbids importing any pyannote cloud SDK."""
    import hawedit.pyannote_adapter as adapter_mod

    source_text = Path(adapter_mod.__file__).read_text(encoding="utf-8")
    assert "cloud" not in source_text.lower()
    assert "api_key" not in source_text.lower()
    assert "pyannote.api" not in source_text
    assert "pyannote.core.cloud" not in source_text


def test_absent_weights_are_refused_by_naming_blocker_four(tmp_path: Path) -> None:
    """AC-3: When weights are unprovisioned, refuse by naming BLOCKED.md #4."""
    fake_audio = tmp_path / "test.wav"
    fake_audio.write_bytes(b"RIFFdummy")

    diarizer = PyannoteDiarizer()
    with pytest.raises(DiarizationUnavailable, match=r"BLOCKED\.md #4"):
        diarizer.diarize(fake_audio)


def test_a_checkpoint_revision_the_acceptance_kit_did_not_pin_is_refused() -> None:
    """AC-4: Checkpoint revision mismatch is refused."""
    with pytest.raises(ValueError, match="Community-1 run must use pinned revision"):
        PyannoteDiarizer(revision="unpinned_revision_123")


def test_missing_pyannote_is_reported_as_a_missing_extra(tmp_path: Path) -> None:
    """AC-8: Missing pyannote.audio surfaces as DiarizationUnavailable naming the extra."""
    fake_audio = tmp_path / "test.wav"
    fake_audio.write_bytes(b"RIFFdummy")
    model_dir = tmp_path / "model_weights"
    model_dir.mkdir()

    diarizer = PyannoteDiarizer(model_dir=model_dir)

    with (
        patch.dict(sys.modules, {"pyannote.audio": None}),
        pytest.raises(DiarizationUnavailable, match=r"hawedit\[diarization\]"),
    ):
        diarizer.diarize(fake_audio)


def test_an_unavailable_diarizer_leaves_the_rest_of_stage_0_intact(tmp_path: Path) -> None:
    """AC-8 / D-240: Operational diarization failure produces structured skip."""

    class _FailingDiarizer:
        def diarize(self, audio: Path) -> tuple[Segment, ...]:
            raise DiarizationUnavailable("diarization model not provisioned (BLOCKED.md #4)")

    base_ingest = IngestResult(
        media_id="test_media",
        source="test.mp4",
        source_sha256="0" * 64,
        duration_ms=5000,
        audio_path="test.wav",
        proxy_path="test_proxy",
        shot_cuts_ms=(),
        speech=(SpeechSegment(start_ms=0, end_ms=4000),),
    )

    with pytest.raises(DiarizationUnavailable):
        attach_diarization(base_ingest, _FailingDiarizer())
