from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from hawedit.boundary import Boundary
from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Output
from hawedit.cover import (
    generate_title_variants,
    score_cover_frame,
    select_cover_frame,
)
from hawedit.delivery import DeliveryRefused, publish_delivery_bundle, reconcile_delivery
from hawedit.measure import (
    AudioMeasurement,
    CaptionMeasurement,
    ClipMeasurement,
    FaceTrackMeasurement,
    FileSummary,
    VideoMeasurement,
)
from hawedit.transcripts import AsrProvenance, Word

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"


def _make_dummy_measurement(duration_ms: int = 4000) -> ClipMeasurement:
    return ClipMeasurement(
        schema=1,
        file=FileSummary(path="/tmp/clip.mp4", sha256="a" * 64, size_bytes=1000),
        video=VideoMeasurement(
            width=1080,
            height=1920,
            fps=25.0,
            fps_ratio="25/1",
            duration_ms=duration_ms,
            frames_count=100,
            bitrate_kbps=3000.0,
            codec="h264",
            pix_fmt="yuv420p",
            color_space="bt709",
            color_transfer="bt709",
            color_primaries="bt709",
        ),
        audio=AudioMeasurement(
            codec="aac",
            sample_rate=48000,
            channels=2,
            duration_ms=duration_ms,
            integrated_lufs=-14.0,
            true_peak_db=-1.0,
            lra_lu=2.0,
            silences=[],
            total_silence_ms=0,
            silence_share=0.0,
        ),
        scenes={"cuts_ms": []},
        faces=FaceTrackMeasurement(
            sample_interval_ms=200,
            samples_count=20,
            face_detected_frames_count=18,
            face_detected_share=0.90,
            median_face_height_share=0.25,
            median_y_center_share=0.38,
            first_frame_face_share=0.25,
        ),
        captions=CaptionMeasurement(
            events_count=5,
            ink_energy_detected_share=1.0,
            median_contrast_ratio=5.0,
        ),
        vmaf=None,
        tool_metadata={"ffmpeg_version": "ffmpeg version 8.1.1"},
    )


def _make_dummy_clip(
    in_ms: int = 0,
    out_ms: int = 4000,
    cover_frame_ms: int | None = None,
    title_variants: tuple[str, ...] = (),
) -> Clip:
    return Clip(
        clip_id="test-clip-1",
        media_id="test-media-1",
        media_sha256="0" * 64,
        in_ms=in_ms,
        out_ms=out_ms,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=Boundary(
            anchor_in_ms=in_ms,
            anchor_out_ms=out_ms,
            final_in_ms=in_ms,
            final_out_ms=out_ms,
            in_extended_by="none",
            out_extended_by="none",
            sentence_complete=True,
        ),
        transcript=ClipTranscript(
            raw_ckb="سڵاو جیهان",
            norm_ckb="سڵاو جیهان",
            en_aux=None,
            words=(
                Word(w="سڵاو", start_ms=in_ms, end_ms=in_ms + 1000, conf=0.9),
                Word(w="جیهان", start_ms=in_ms + 1000, end_ms=out_ms, conf=0.9),
            ),
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2"),
        ),
        output=Output(
            title_ckb="سەردێڕی سەرەکی",
            description_ckb="وەسفی کورت",
            crop_target="center_crop",
            caption_style="word_highlight",
            durations=(4,),
            title_variants_ckb=title_variants,
            cover_frame_ms=cover_frame_ms,
        ),
    )


def test_generate_title_variants_produces_three_distinct_kurdish_variants() -> None:
    """AC-3: generate_title_variants produces 3 non-empty Kurdish Sorani strings."""
    base = "وتاری گرنگی ئەمڕۆ"
    v1, v2, v3 = generate_title_variants(base, hook_type="question")

    assert v1 == base
    assert v2 == f"ئایا {base}؟"
    assert "وەڵامی گرنگ:" in v3
    assert len({v1, v2, v3}) == 3

    # Reject empty title
    with pytest.raises(ValueError, match="cannot be empty"):
        generate_title_variants("   ")


def test_output_contract_roundtrips_title_variants_and_cover_frame_ms() -> None:
    """AC-4: Output contract serializes and deserializes title_variants_ckb and cover_frame_ms."""
    out = Output(
        title_ckb="سەردێڕ",
        description_ckb="وەسف",
        crop_target="face_tracked",
        caption_style="word_highlight",
        durations=(30,),
        title_variants_ckb=("سەردێڕی ١", "سەردێڕی ٢", "سەردێڕی ٣"),
        cover_frame_ms=1500,
    )

    data = out.to_dict()
    assert data["title_variants_ckb"] == ["سەردێڕی ١", "سەردێڕی ٢", "سەردێڕی ٣"]
    assert data["cover_frame_ms"] == 1500

    deserialized = Output.from_dict(data)
    assert deserialized.title_variants_ckb == ("سەردێڕی ١", "سەردێڕی ٢", "سەردێڕی ٣")
    assert deserialized.cover_frame_ms == 1500

    # Backward compatibility with legacy JSON missing the new fields
    del data["title_variants_ckb"]
    del data["cover_frame_ms"]
    legacy = Output.from_dict(data)
    assert legacy.title_variants_ckb == ()
    assert legacy.cover_frame_ms is None


def test_score_cover_frame_evaluates_synthetic_frame() -> None:
    """AC-1: score_cover_frame returns None for blank frame with no face."""
    from hawedit.cover import _load_cascades

    frontal, eye = _load_cascades()
    blank = np.zeros((360, 640, 3), dtype=np.uint8)
    cand = score_cover_frame(blank, 1000, frontal, eye)
    assert cand is None


def test_select_cover_frame_on_real_video(tmp_path: Path) -> None:
    """AC-1, AC-2: select_cover_frame evaluates frames and writes a valid PNG thumbnail."""
    if not FIXTURE.is_file():
        pytest.skip(f"Fixture not found: {FIXTURE}")

    out_png = tmp_path / "cover.png"
    result = select_cover_frame(
        video_path=FIXTURE,
        output_png_path=out_png,
        in_ms=500,
        out_ms=3500,
        sample_interval_ms=500,
    )

    assert out_png.is_file()
    assert out_png.stat().st_size > 0
    assert 500 <= result.chosen_time_ms <= 3500
    assert result.candidates_evaluated > 0

    # Verify extracted image is a readable OpenCV image matching fixture dimensions
    img = cv2.imread(str(out_png))
    assert img is not None
    assert img.shape[0] > 0
    assert img.shape[1] > 0


def test_reconcile_delivery_enforces_clause_eleven_cover_boundary() -> None:
    """AC-5: reconcile_delivery enforces Clause 11 (cover_frame_ms inside clip boundary)."""
    meas = _make_dummy_measurement(duration_ms=4000)

    # Valid clip-relative cover frame (1500ms in [0, 4000ms])
    valid_clip = _make_dummy_clip(in_ms=0, out_ms=4000, cover_frame_ms=1500)
    reconcile_delivery(valid_clip, meas)

    # Valid source-absolute cover frame (10500ms in [10000, 14000ms])
    meas_source = _make_dummy_measurement(duration_ms=4000)
    valid_source_clip = _make_dummy_clip(in_ms=10000, out_ms=14000, cover_frame_ms=10500)
    reconcile_delivery(valid_source_clip, meas_source)

    # Invalid cover frame (50000ms outside [0, 4000ms])
    broken_clip = _make_dummy_clip(in_ms=0, out_ms=4000, cover_frame_ms=50000)
    with pytest.raises(DeliveryRefused, match="cover_frame_out_of_bounds"):
        reconcile_delivery(broken_clip, meas)


def test_publish_delivery_bundle_includes_cover_image(tmp_path: Path) -> None:
    """AC-5: publish_delivery_bundle writes cover.png when cover_image_path is supplied."""
    out_dir = tmp_path / "delivered"
    clip = _make_dummy_clip(in_ms=0, out_ms=4000, cover_frame_ms=1000)

    dummy_cover = tmp_path / "dummy_cover.png"
    dummy_cover.write_bytes(b"\x89PNG\r\n\x1a\nfake_image_bytes")

    bundle = publish_delivery_bundle(
        output_dir=out_dir,
        clip=clip,
        source_media_path="source.mp4",
        fps=25.0,
        cover_image_path=dummy_cover,
    )

    assert "cover" in bundle
    cover_file = bundle["cover"]
    assert cover_file.is_file()
    assert cover_file.name == f"{clip.clip_id}.cover.png"
    assert cover_file.read_bytes() == dummy_cover.read_bytes()


def test_select_cover_frame_on_ep29_extracts_face_thumbnail(tmp_path: Path) -> None:
    """Proof B: select_cover_frame on ep29 selects a sharp face frame with open eyes."""
    ep29_clip = ROOT / "work" / "ep29-VbX8UWwl1c4-s25-25" / "ep29-VbX8UWwl1c4-s25-25.mp4"
    if not ep29_clip.is_file():
        pytest.skip("ep29 clip not available")

    out_png = tmp_path / "ep29_cover.png"
    result = select_cover_frame(
        video_path=ep29_clip,
        output_png_path=out_png,
        in_ms=0,
        out_ms=20000,
        sample_interval_ms=1000,
    )

    assert out_png.is_file()
    assert out_png.stat().st_size > 0
    assert result.face_share > 0.15
    assert result.sharpness > 100.0
    assert result.eyes_count >= 1
    assert result.score > 50.0

    img = cv2.imread(str(out_png))
    assert img is not None
    assert img.shape == (1920, 1080, 3)
