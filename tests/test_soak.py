"""Soak and resilience harness testing edge inputs, corrupt files, and timeout bounds.

Satisfies Claim R1 and Phase 1.6 of specs/pro-grade-program/road-to-number-one.md:
ensures corrupt, truncated, 0-byte, and silent files fail fast with explicit IngestError
within strict timeout bounds, never causing hangs, deadlocks, or silent fallbacks.
"""

from __future__ import annotations

import time
import wave
from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.condenser import condense_multiple_arcs
from hawedit.ingest import IngestError, detect_speech, ingest
from hawedit.sentences import Sentence
from hawedit.transcripts import Word

needs_ffmpeg = pytest.mark.skipif(
    find_ffmpeg() is None,
    reason="no ffmpeg — set HAWEDIT_FFMPEG",
)


@needs_ffmpeg
def test_soak_empty_file_fails_fast_with_ingest_error(tmp_path: Path) -> None:
    """0-byte file passed to ingest raises IngestError in < 2 seconds without hanging."""
    empty_file = tmp_path / "zero_bytes.mp4"
    empty_file.write_bytes(b"")

    start_time = time.monotonic()
    with pytest.raises(IngestError):
        ingest(empty_file, tmp_path / "work_empty")
    elapsed = time.monotonic() - start_time
    assert elapsed < 2.0, f"Empty file ingest took too long: {elapsed:.2f}s"


@needs_ffmpeg
def test_soak_corrupt_file_fails_fast_with_ingest_error(tmp_path: Path) -> None:
    """Corrupt garbage file passed to ingest raises IngestError in < 2 seconds without hanging."""
    corrupt_file = tmp_path / "garbage.mp4"
    corrupt_file.write_bytes(b"NOT_A_REAL_VIDEO_HEADER_RANDOM_DATA_1234567890" * 20)

    start_time = time.monotonic()
    with pytest.raises(IngestError):
        ingest(corrupt_file, tmp_path / "work_corrupt")
    elapsed = time.monotonic() - start_time
    assert elapsed < 2.0, f"Corrupt file ingest took too long: {elapsed:.2f}s"


@needs_ffmpeg
def test_soak_truncated_mp4_header_fails_cleanly(tmp_path: Path) -> None:
    """Truncated MP4 with incomplete ftyp atom fails with IngestError without deadlocking."""
    truncated = tmp_path / "truncated.mp4"
    # Valid ftyp box size (32 bytes) but file is cut short at 8 bytes
    truncated.write_bytes(b"\x00\x00\x00\x20ftypisom")

    start_time = time.monotonic()
    with pytest.raises(IngestError):
        ingest(truncated, tmp_path / "work_truncated")
    elapsed = time.monotonic() - start_time
    assert elapsed < 2.0, f"Truncated file ingest took too long: {elapsed:.2f}s"


def test_soak_silent_audio_produces_no_false_speech(tmp_path: Path) -> None:
    """Pure silence WAV audio file yields 0 speech segments from VAD without crash or hang."""
    silent_wav = tmp_path / "silence.wav"
    # Create 3 seconds of 16kHz mono 16-bit silence
    num_samples = 16_000 * 3
    with wave.open(str(silent_wav), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * num_samples)

    start_time = time.monotonic()
    segments = detect_speech(silent_wav)
    elapsed = time.monotonic() - start_time
    assert elapsed < 5.0
    assert len(segments) == 0, f"Expected 0 speech segments in silence, got {len(segments)}"


def test_soak_synthetic_60min_multi_arc_workload() -> None:
    """60-minute long conversation (180 sentences) condenses into ranked arcs in < 1s."""
    # Build 180 sentences spanning 3600 seconds (each sentence ~20s)
    sentences: list[Sentence] = []
    for i in range(180):
        start_ms = i * 20_000
        mid_ms = start_ms + 9_000
        end_ms = start_ms + 19_500
        w1 = Word(w=f"وشەی_دەستپێک_{i}", start_ms=start_ms, end_ms=mid_ms, conf=0.99)
        w2 = Word(w=f"وشەی_کۆتایی_{i}", start_ms=mid_ms + 100, end_ms=end_ms, conf=0.98)
        sentences.append(Sentence(words=(w1, w2), complete=True))

    start_time = time.monotonic()
    plans = condense_multiple_arcs(
        sentences,
        max_clips=5,
        target_duration_ms=50_000,
        min_duration_ms=25_000,
        max_duration_ms=60_000,
    )
    elapsed = time.monotonic() - start_time
    assert elapsed < 1.0, f"60-min condensation took too long: {elapsed:.2f}s"
    assert len(plans) == 5
    for idx, plan in enumerate(plans, start=1):
        assert plan.story_id == f"clip-{idx:02d}"
        assert plan.condensed_duration_ms <= 60_000
        assert plan.condensed_duration_ms >= 25_000
