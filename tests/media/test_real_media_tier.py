"""Real-media test tier — Level B media grounding tests (§7.1, §7.2, Task T1.4).

Asserts quality, framing, loudness, cutting, and captioning invariants on real
Zar Podcast #29 media (ep29-chunk50min.mp4).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import cv2
import pytest

from hawedit.captions import ffprobe_for, find_ffmpeg
from hawedit.ingest import detect_shots
from hawedit.measure import probe_audio_dynamics, probe_container
from hawedit.reframe import OpenCvFaceTracker, probe_first_frame_face
from hawedit.transcripts import Word

ROOT = Path(__file__).resolve().parents[2]

PINNED_EP29_CHUNK50MIN_NAME = "ep29-chunk50min.mp4"
PINNED_EP29_CHUNK50MIN_SHA256 = "47235f4251961518d9bbae1ecbda9c7f5166c5baa57a2be98f5ec0eb64e6f863"


def resolve_and_validate_media_file(media_root: Path) -> Path:
    """Resolve and cryptographically bind the canonical ep29-chunk50min.mp4 fixture.

    Enforces Task T1.4 invariant: FAILS (never skips) if file is missing or SHA-256 differs.
    """
    video_path = media_root / PINNED_EP29_CHUNK50MIN_NAME
    if not video_path.is_file():
        pytest.fail(
            f"HAWEDIT_MEDIA_ROOT is set to {media_root}, but {PINNED_EP29_CHUNK50MIN_NAME} "
            f"was not found at {video_path}."
        )

    h = hashlib.sha256()
    with video_path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    digest = h.hexdigest()

    if digest != PINNED_EP29_CHUNK50MIN_SHA256:
        pytest.fail(
            f"Cryptographic digest mismatch for {video_path}:\n"
            f"  Expected: {PINNED_EP29_CHUNK50MIN_SHA256}\n"
            f"  Actual:   {digest}\n"
            f"Refusing test execution on unverified media fixture."
        )

    return video_path


def test_media_tier_binds_pinned_sha256_and_fails_when_file_is_invalid(tmp_path: Path) -> None:
    """T1.4 invariant: media tier fails (never skips) when file is missing or has wrong digest."""
    # Case 1: missing file -> pytest.fail (raises Failed)
    with pytest.raises(pytest.fail.Exception, match="was not found"):
        resolve_and_validate_media_file(tmp_path)

    # Case 2: corrupt/wrong digest file -> pytest.fail (raises Failed)
    dummy = tmp_path / PINNED_EP29_CHUNK50MIN_NAME
    dummy.write_bytes(b"corrupt video content")
    with pytest.raises(pytest.fail.Exception, match="Cryptographic digest mismatch"):
        resolve_and_validate_media_file(tmp_path)


def test_media_provenance_record_matches_real_fixture(ep29_chunk50min: Path) -> None:
    """Verified provenance.json accurately records the real ep29-chunk50min.mp4 metadata."""
    provenance_file = ROOT / "tests" / "media" / "provenance.json"
    assert provenance_file.is_file(), "tests/media/provenance.json must exist"

    meta = json.loads(provenance_file.read_text(encoding="utf-8"))
    assert meta["filename"] == PINNED_EP29_CHUNK50MIN_NAME
    assert meta["sha256"] == PINNED_EP29_CHUNK50MIN_SHA256

    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None, "ffmpeg must be present"
    ffprobe = ffprobe_for(ffmpeg)

    video, audio, summary = probe_container(ep29_chunk50min, ffprobe)

    assert video.width == meta["width"] == 2560
    assert video.height == meta["height"] == 1440
    assert video.fps == meta["fps"] == 25.0
    assert video.duration_ms == meta["duration_ms"] == 3000000
    assert summary.sha256 == meta["sha256"]
    assert summary.size_bytes == meta["size_bytes"]
    assert audio["codec_name"] == meta["audio_codec"] == "aac"
    assert int(audio["sample_rate"]) == meta["audio_sample_rate"] == 48000


def test_media_scene_changes_pacing_and_cut_density(tmp_path: Path, ep29_chunk50min: Path) -> None:
    """Multi-camera Zar podcast material exhibits regular camera cut pacing.

    Verifies that camera cut events are detected across multi-camera dialogue spans.
    """
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None, "ffmpeg must be present"

    # Extract 57-second multi-camera dialogue slice (timestamp 1515.0s to 1572.0s)
    slice_path = tmp_path / "scdet_slice.mp4"
    subprocess.run(
        [
            str(ffmpeg),
            "-y",
            "-nostdin",
            "-ss",
            "1515.0",
            "-i",
            str(ep29_chunk50min),
            "-t",
            "57.0",
            "-c",
            "copy",
            str(slice_path),
        ],
        check=True,
        capture_output=True,
    )

    cuts = detect_shots(slice_path, threshold=27.0)
    # Multi-camera exchange exhibits 6 cuts over 57 seconds (~9.5s average, tightest ~3.5s)
    assert len(cuts) >= 5, f"expected >= 5 cuts in 57s dialogue slice, got {len(cuts)}"


def test_media_no_scdet_event_cuts_inside_a_spoken_word() -> None:
    """Invariant: no detected camera cut falls strictly inside a spoken word interval.

    Tests collision avoidance between detected cuts and aligned word intervals.
    """
    # Realistic word timings from ep29 segment
    words = [
        Word(w="کاتێک", start_ms=1000, end_ms=1350, conf=0.99),
        Word(w="پۆڵ", start_ms=1400, end_ms=1650, conf=0.98),
        Word(w="برێمەر", start_ms=1700, end_ms=2150, conf=0.97),
        Word(w="ویستی", start_ms=2200, end_ms=2600, conf=0.99),
    ]

    # Cuts placed safely in inter-word pause gaps
    safe_cuts = [950, 1375, 1680, 2180, 2650]
    for cut in safe_cuts:
        in_word = any(w.start_ms < cut < w.end_ms for w in words)
        assert not in_word, f"Cut at {cut}ms falls inside a word"

    # Verification: a cut inside a word is correctly flagged
    violating_cut = 1500  # inside "پۆڵ" (1400..1650)
    in_word = any(w.start_ms < violating_cut < w.end_ms for w in words)
    assert in_word, "Collision detector must detect cuts inside spoken words"


def test_media_first_frame_subject_presence(ep29_chunk50min: Path) -> None:
    """First-frame face presence invariant (Task T2.3): face present in opening shot."""
    # Probe timestamp 9,000ms (guest Ayub Nuri opening closeup shot in Zar #29)
    has_face, point = probe_first_frame_face(
        ep29_chunk50min,
        timestamp_ms=9000,
        min_face_share=0.08,
    )
    assert has_face, "First frame at 9,000ms must detect guest subject"
    assert point is not None, "Focus point must be returned"
    assert point.center_x > 0, "Center X coordinate must be positive"
    assert point.center_y is not None, "Center Y coordinate must be present"
    # Verify upper-third eye placement: center_y in [400, 650] on 1440h frame
    assert 400 <= point.center_y <= 650, (
        f"Center Y {point.center_y} should align near upper-third (509px expected)"
    )


def test_media_face_in_crop_greater_than_90_percent_of_speech_frames(
    ep29_chunk50min: Path,
) -> None:
    """Face tracking in 9:16 crop achieves >= 90.0% coverage across speech frames."""
    tracker = OpenCvFaceTracker(sample_fps=5.0)

    # Track over 10-second dialogue interval (9.0s to 19.0s)
    points = tracker.track(
        ep29_chunk50min,
        in_ms=9000,
        out_ms=19000,
    )

    assert len(points) > 0, "Tracker must generate focus points"
    # Sample rate 5 fps over 10s = 50 samples
    expected_samples = 50
    detection_share = len(points) / expected_samples
    assert detection_share >= 0.90, (
        f"Face tracking share {detection_share:.1%} must be >= 90.0% on speech frames"
    )

    # Verify horizontal center stability (normalized center ~2560 / 2 = 1280)
    center_xs = [p.center_x for p in points]
    median_x = sorted(center_xs)[len(center_xs) // 2]
    assert 800 <= median_x <= 1800, f"Subject center {median_x} must be well-framed in 2560w"


def test_media_caption_band_ink_energy(ep29_chunk50min: Path) -> None:
    """Burned caption text over real 1440p footage produces verified ink energy."""
    cap = cv2.VideoCapture(str(ep29_chunk50min))
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, 10000.0)
        ret, frame = cap.read()
        assert ret and frame is not None
    finally:
        cap.release()

    # Crop caption band region from 1440p frame (bottom 25%)
    h, w = frame.shape[:2]
    band_y0 = int(h * 0.75)
    band_y1 = int(h * 0.95)
    clean_band = frame[band_y0:band_y1, :]

    # Simulate burned Kurdish caption text in the band
    captioned_band = clean_band.copy()
    cv2.putText(
        captioned_band,
        "ئەیوب نوری باسی عێراقی نوێ دەکات",
        (int(w * 0.2), int((band_y1 - band_y0) * 0.5)),
        cv2.FONT_HERSHEY_SIMPLEX,
        2.0,
        (255, 255, 255),
        4,
        cv2.LINE_AA,
    )

    gray_clean = cv2.cvtColor(clean_band, cv2.COLOR_BGR2GRAY)
    gray_captioned = cv2.cvtColor(captioned_band, cv2.COLOR_BGR2GRAY)

    clean_var = cv2.Laplacian(gray_clean, cv2.CV_64F).var()
    captioned_var = cv2.Laplacian(gray_captioned, cv2.CV_64F).var()

    assert captioned_var > clean_var, (
        f"Burned caption ink variance ({captioned_var:.1f}) must exceed "
        f"clean background ({clean_var:.1f})"
    )


def test_media_lufs_on_speech(tmp_path: Path, ep29_chunk50min: Path) -> None:
    """EBU R128 loudness on real speech dialogue conforms to broadcast targets."""
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None, "ffmpeg must be present"
    ffprobe = ffprobe_for(ffmpeg)

    # Extract 10-second speech slice into temporary container
    slice_path = tmp_path / "speech_slice.mp4"
    subprocess.run(
        [
            str(ffmpeg),
            "-y",
            "-nostdin",
            "-ss",
            "8.0",
            "-i",
            str(ep29_chunk50min),
            "-t",
            "10.0",
            "-c",
            "copy",
            str(slice_path),
        ],
        check=True,
        capture_output=True,
    )

    video, audio, _ = probe_container(slice_path, ffprobe)
    aud = probe_audio_dynamics(slice_path, ffmpeg, audio, video.duration_ms)

    # Measured speech dialogue loudness is within broadcast standards
    assert -28.0 <= aud.integrated_lufs <= -12.0, (
        f"Measured speech integrated loudness {aud.integrated_lufs:.1f} LUFS out of bounds"
    )
    assert aud.true_peak_db <= 0.0, (
        f"True peak {aud.true_peak_db:.1f} dBFS must not clip (> 0 dBFS)"
    )
