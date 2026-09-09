"""Unit tests for the automated Sanity Gate and Quality Audit suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.condenser import BeatKind, CondensedStoryPlan, StoryBeat, StorySummary
from hawedit.sanity_gate import (
    QualityAuditReport,
    SanityGate,
    SanityGateFailureError,
    check_face_presence,
    check_narrative_integrity,
    check_subtitles,
    parse_ebur128_stats,
)


def _make_dummy_story_plan(
    headline: str = "هەڕەشەی کوشتن",
    summary: str = "پوختەی چیڕۆکی میوان لە بەغدا",
    duration_ms: int = 50_000,
) -> CondensedStoryPlan:
    s_summary = StorySummary(
        headline_kurdish=headline,
        summary_kurdish=summary,
        virality_score=90.0,
        core_topic="تیرۆر",
        key_entities=("بەغدا",),
    )
    beat = StoryBeat(
        beat_id="b0",
        beat_kind=BeatKind.HOOK,
        sentence_indices=(0,),
        in_ms=0,
        out_ms=duration_ms,
        importance_score=0.9,
        summary_kurdish="دەستپێک",
    )
    return CondensedStoryPlan(
        story_id="test-plan",
        summary=s_summary,
        beats=(beat,),
        retained_sentence_indices=(0,),
        pruned_sentence_indices=(),
        retained_spans=((0, duration_ms),),
        total_source_duration_ms=duration_ms,
        condensed_duration_ms=duration_ms,
        prune_ratio=0.0,
    )


def test_quality_audit_report_invariants() -> None:
    """QualityAuditReport serializes to dict and reports pass/fail correctly."""
    report = QualityAuditReport(
        passed=True,
        framing_pass=True,
        subtitles_pass=True,
        audio_pass=True,
        story_pass=True,
        detected_faces_per_shot={"shot_0": 1, "shot_1": 2},
        audio_lufs=-16.5,
        audio_true_peak_dbfs=-1.2,
        subtitle_max_chars_per_line=12,
        subtitle_font_size_pt=115,
        subtitle_margin_v=260,
        defect_messages=(),
    )
    assert report.passed is True
    data = report.to_dict()
    assert data["passed"] is True
    assert data["audio_lufs"] == -16.5
    assert len(data["defect_messages"]) == 0


def test_check_subtitles_valid_and_invalid(tmp_path: Path) -> None:
    """Valid ASS subtitles pass legibility; sub-100pt font or long lines fail."""
    valid_ass = tmp_path / "valid.ass"
    style_header = (
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding"
    )
    style_pop = (
        "Style: PopKurdish,Vazirmatn,115,&H00FFFFFF,&H0000E5FF,&H00000000,&H80000000,"
        "1,0,0,0,100,100,0,0,1,8,0,2,30,30,260,1"
    )
    valid_ass.write_text(
        f"""[Script Info]
Title: Test
ScriptType: v4.00+

[V4+ Styles]
{style_header}
{style_pop}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:01.50,PopKurdish,,0,0,260,,ئەمە تاقیکردنەوەیە
""",
        encoding="utf-8",
    )

    passed, max_chars, font_size, margin_v, defects = check_subtitles(valid_ass)
    assert passed is True
    assert font_size == 115
    assert margin_v == 260
    assert len(defects) == 0

    # Invalid ASS: font size 60pt (< 100pt) and long lines
    invalid_ass = tmp_path / "invalid.ass"
    style_bad = (
        "Style: BadStyle,Arial,60,&H00FFFFFF,&H0000E5FF,&H00000000,&H80000000,"
        "1,0,0,0,100,100,0,0,1,8,0,2,30,30,100,1"
    )
    long_line = "ئەم دێڕە زۆر زۆر درێژە و لە بیست پیت زیاترە بۆیە دەبێت شکست بهێنێت"
    invalid_ass.write_text(
        f"""[V4+ Styles]
{style_header}
{style_bad}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:05.50,BadStyle,,0,0,100,,{long_line}
""",
        encoding="utf-8",
    )

    passed, max_chars, font_size, margin_v, defects = check_subtitles(invalid_ass)
    assert passed is False
    assert font_size == 60
    assert any("Font size 60pt is below minimum 100pt" in d for d in defects)
    assert any("MarginV 100px is below safe margin" in d for d in defects)
    assert any("exceeds max 20" in d for d in defects)


def test_parse_ebur128_stats() -> None:
    """Parse FFmpeg ebur128 output log and validate broadcast audio loudness bounds."""
    sample_ffmpeg_output = """
    [Parsed_ebur128_0 @ 000001] Summary:
      Integrated loudness:
        I:         -16.2 LUFS
        Threshold: -26.3 LUFS
      Loudness range:
        LRA:         5.4 LU
      True peak:
        Peak:       -1.5 dBFS
    """
    lufs, peak, passed, defects = parse_ebur128_stats(sample_ffmpeg_output)
    assert passed is True
    assert lufs == -16.2
    assert peak == -1.5
    assert len(defects) == 0

    # Test clipped audio
    clipped_output = """
    [Parsed_ebur128_0 @ 000001] Summary:
      Integrated loudness:
        I:         -12.0 LUFS
      True peak:
        Peak:        0.5 dBFS
    """
    lufs, peak, passed, defects = parse_ebur128_stats(clipped_output)
    assert passed is False
    assert any("True Peak 0.5 dBFS exceeds -1.0 dBFS" in d for d in defects)
    assert any("Integrated loudness -12.0 LUFS outside range" in d for d in defects)


def test_check_narrative_integrity() -> None:
    """Check narrative integrity flags empty headline, empty summary, or invalid duration."""
    valid_plan = _make_dummy_story_plan()
    passed, defects = check_narrative_integrity(valid_plan)
    assert passed is True
    assert len(defects) == 0

    # Invalid: duration too short (< 25s)
    short_plan = _make_dummy_story_plan(duration_ms=10_000)
    passed, defects = check_narrative_integrity(short_plan)
    assert passed is False
    assert any("duration 10.0s is below 25s" in d for d in defects)


def test_check_face_presence_missing_and_corrupt_file(tmp_path: Path) -> None:
    """Missing or unopenable video file fails immediately reporting explicit failure."""
    missing = tmp_path / "does_not_exist.mp4"
    passed, faces, defects = check_face_presence(missing, [(0.0, 1.0)])
    assert passed is False
    assert len(faces) == 0
    assert any("Video file does not exist" in d for d in defects)

    # Corrupt/unopenable file
    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"NOT_A_VIDEO")
    passed_c, faces_c, defects_c = check_face_presence(corrupt, [(0.0, 1.0)])
    assert passed_c is False
    assert len(faces_c) == 0
    assert any("Could not open video file" in d for d in defects_c)


def test_check_face_presence_on_fixture() -> None:
    """Run check_face_presence on fixture video to verify frame sampling and cleanup."""
    fixture = Path(__file__).resolve().parent / "fixtures" / "kurdish-speech-3cuts.mp4"
    if not fixture.is_file():
        pytest.skip("Fixture video missing")
    passed, faces, defects = check_face_presence(fixture, [(0.0, 0.5), (0.5, 1.0)])
    # The fixture is low-res without face detection in tight crop, should fail framing safely
    assert isinstance(faces, dict)
    assert len(faces) == 2
    assert passed is False
    assert len(defects) >= 1


def test_sanity_gate_run_full_audit_strict_fail_stop(tmp_path: Path) -> None:
    """SanityGate.run_full_audit aggregates defects.

    In strict mode it raises SanityGateFailureError.
    """
    invalid_ass = tmp_path / "subs.ass"
    invalid_ass.write_text("[V4+ Styles]\n[Events]\n", encoding="utf-8")
    short_plan = _make_dummy_story_plan(duration_ms=10_000)
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"dummy")

    # Non-strict mode returns report with passed=False
    report = SanityGate.run_full_audit(
        fake_video,
        invalid_ass,
        short_plan,
        [(0.0, 1.0)],
        strict_fail_stop=False,
    )
    assert report.passed is False
    assert len(report.defect_messages) > 0

    # Strict mode raises SanityGateFailureError
    with pytest.raises(SanityGateFailureError, match="Sanity Gate FAILED"):
        SanityGate.run_full_audit(
            fake_video,
            invalid_ass,
            short_plan,
            [(0.0, 1.0)],
            strict_fail_stop=True,
        )


def test_check_face_presence_detects_consecutive_dead_frames() -> None:
    """CD-10: Dialogue shots dropping to 0 detected faces are flagged with Dead Frame Detected."""
    fixture = Path(__file__).resolve().parent / "fixtures" / "kurdish-speech-3cuts.mp4"
    if not fixture.is_file():
        pytest.skip("Fixture video missing")

    # Inspect shot spanning 0.0s..2.0s
    passed, faces, defects = check_face_presence(fixture, [(0.0, 2.0)])
    assert passed is False
    assert any("Dead Frame Detected" in d for d in defects)
    assert any("0 detected faces" in d for d in defects)
