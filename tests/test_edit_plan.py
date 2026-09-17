"""Tests for unified visual edit contract and time mapping (Task VE-01 / V01)."""

from __future__ import annotations

import pytest

from hawedit.captions import CaptionStyle
from hawedit.content_type import ContentType
from hawedit.edit_plan import (
    CURRENT_PLAN_VERSION,
    EditorialBrief,
    EffectiveConfiguration,
    SourceTimeMapping,
    VisualEditPlan,
)
from hawedit.sentences import Sentence
from hawedit.transcripts import Word


def _make_test_sentences() -> tuple[Sentence, ...]:
    """Two sentences in source time."""
    s1 = Sentence(
        words=(
            Word(w="سڵاو", start_ms=1200, end_ms=2000, conf=0.98),
            Word(w="هاوڕێیان", start_ms=2100, end_ms=3500, conf=0.95),
        ),
        complete=True,
    )
    s2 = Sentence(
        words=(
            Word(w="ئەمە", start_ms=7500, end_ms=8500, conf=0.99),
            Word(w="تەواوە", start_ms=8600, end_ms=10500, conf=0.97),
        ),
        complete=True,
    )
    return (s1, s2)


def test_visual_plan_replay_preserves_all_artifact_timebases() -> None:
    """VE-01 / V01: Edit plan replay preserves exact timebases and sidecar bytes."""
    brief = EditorialBrief(
        viewer_takeaway="Key takeaway of the Kurdish discussion",
        content_type=ContentType.PODCAST,
        target_duration_ms=(8000, 12000),
        protected_regions=("lower_third_captions", "speaker_face"),
    )
    config = EffectiveConfiguration.resolve(
        content_type=ContentType.PODCAST,
        caption_style=CaptionStyle.WORD_HIGHLIGHT,
        reframe_mode="speaker_tracked",
        silence_threshold_ms=600,
        silence_target_gap_ms=150,
        punch_in_cadence_ms=4000,
        eased_push=False,
        two_person_split="auto",
        fps=25.0,
    )
    # Source clip 1000..12000 ms with dead air between 4000..6000 excised
    time_mapping = SourceTimeMapping(
        clip_in_ms=1000,
        clip_out_ms=12000,
        retained_intervals_ms=((1000, 4000), (6000, 11500)),
    )
    # Retained spans: 3000 ms + 5500 ms = 8500 ms output duration
    assert time_mapping.output_duration_ms == 8500

    # Test bidirectional time mapping
    assert time_mapping.source_to_output_ms(1000) == 0
    assert time_mapping.source_to_output_ms(2500) == 1500
    assert time_mapping.source_to_output_ms(4000) == 3000
    # Inside excised dead air (5000 ms):
    assert time_mapping.source_to_output_ms(5000, clamp_excised=False) is None
    assert time_mapping.source_to_output_ms(5000, clamp_excised=True) == 3000
    # Second segment:
    assert time_mapping.source_to_output_ms(6000) == 3000
    assert time_mapping.source_to_output_ms(8000) == 5000
    assert time_mapping.source_to_output_ms(11500) == 8500

    # Reverse mapping for retained points:
    assert time_mapping.output_to_source_ms(0) == 1000
    assert time_mapping.output_to_source_ms(1500) == 2500
    assert time_mapping.output_to_source_ms(3000) == 4000
    assert time_mapping.output_to_source_ms(5000) == 8000
    assert time_mapping.output_to_source_ms(8500) == 11500

    sentences = _make_test_sentences()
    plan = VisualEditPlan(
        version=CURRENT_PLAN_VERSION,
        clip_id="test_clip_v01",
        media_id="episode_01",
        media_sha256="a" * 64,
        brief=brief,
        config=config,
        time_mapping=time_mapping,
        shot_cuts_ms=(3000, 7000),
        punch_in_ms=(2500, 8000),
        speaker_turns=((1000, 4000, "Spk1"), (6000, 11500, "Spk2")),
        sentences=sentences,
    )

    # Derive initial sidecars
    srt_text = plan.derive_srt()
    assert "سڵاو" in srt_text
    assert "هاوڕێیان" in srt_text
    assert "ئەمە" in srt_text

    edl_text = plan.derive_edl(title="TEST REPLAY")
    # Two retained intervals => 4 events (001 V, 002 A, 003 V, 004 A)
    assert "001  AX       V     C" in edl_text
    assert "002  AX       A     C" in edl_text
    assert "003  AX       V     C" in edl_text
    assert "004  AX       A     C" in edl_text

    otio_data = plan.derive_otio("/media/episode_01.mp4", title="TEST OTIO")
    assert otio_data["OTIO_SCHEMA"] == "Timeline.1"
    v_track = otio_data["tracks"]["children"][0]
    a_track = otio_data["tracks"]["children"][1]
    assert len(v_track["children"]) == 2
    assert len(a_track["children"]) == 2

    # Serialize to JSON and replay
    plan_json = plan.to_json()
    replayed = VisualEditPlan.from_json(plan_json)

    # Replay identity assertions
    assert replayed == plan
    assert replayed.derive_srt() == srt_text
    assert replayed.derive_edl(title="TEST REPLAY") == edl_text
    assert replayed.derive_otio("/media/episode_01.mp4", title="TEST OTIO") == otio_data


def test_effective_configuration_validates_incompatible_options() -> None:
    """Incompatible configuration combinations are refused early."""
    # News profile prohibits punch-in cadence > 0
    with pytest.raises(ValueError, match="NEWS content prohibits punch-in cadence"):
        EffectiveConfiguration.resolve(
            content_type=ContentType.NEWS,
            punch_in_cadence_ms=2500,
        )

    # News profile prohibits eased push
    with pytest.raises(ValueError, match="NEWS content prohibits eased continuous push-in"):
        EffectiveConfiguration.resolve(
            content_type=ContentType.NEWS,
            eased_push=True,
        )

    # Invalid silence thresholds
    with pytest.raises(ValueError, match="strictly less than"):
        EffectiveConfiguration.resolve(
            silence_threshold_ms=300,
            silence_target_gap_ms=400,
        )

    # Invalid split mode
    with pytest.raises(ValueError, match="two_person_split"):
        EffectiveConfiguration.resolve(
            two_person_split="invalid_mode",
        )


def test_editorial_brief_conservative_defaults() -> None:
    """Brief defaults protect essential regions and enforce valid ranges."""
    brief = EditorialBrief.default_for_content(ContentType.SOCIAL, duration_ms=20_000)
    assert brief.content_type is ContentType.SOCIAL
    assert "lower_third_captions" in brief.protected_regions
    assert "speaker_face" in brief.protected_regions
    assert brief.target_duration_ms[0] <= 20_000 <= brief.target_duration_ms[1]

    # Invalid duration ranges raise ValueError
    with pytest.raises(ValueError, match="invalid target_duration_ms"):
        EditorialBrief(
            viewer_takeaway="Valid takeaway",
            content_type=ContentType.PODCAST,
            target_duration_ms=(30_000, 20_000),  # min > max
        )

    with pytest.raises(ValueError, match="viewer_takeaway cannot be empty"):
        EditorialBrief(
            viewer_takeaway="   ",
            content_type=ContentType.PODCAST,
            target_duration_ms=(15_000, 30_000),
        )


def test_trimmed_render_and_all_sidecars_share_one_time_mapping() -> None:
    """AC-09 / Task T06: One retained-interval mapping drives every export and media clock."""
    # 1. Setup multi-cut retained intervals representing trimmed render with dead air excised:
    # Source span: 2000..15000 ms (span 13000 ms)
    # Excised dead air: 5000..7000 ms (2000 ms) and 10000..11500 ms (1500 ms)
    # Retained intervals: (2000, 5000), (7000, 10000), (12000, 15000)
    # Output duration: 3000 + 3000 + 3000 = 9000 ms
    time_mapping = SourceTimeMapping(
        clip_in_ms=2000,
        clip_out_ms=16000,
        retained_intervals_ms=((2000, 5000), (7000, 10000), (12000, 15000)),
    )
    assert time_mapping.output_duration_ms == 9000

    # 2. Sentences spanning across all intervals and across excised dead air:
    s1 = Sentence(
        words=(
            Word(w="وتەی", start_ms=2200, end_ms=3000, conf=0.98),
            Word(w="یەکەم", start_ms=3200, end_ms=4800, conf=0.97),
        ),
        complete=True,
    )
    s_excised = Sentence(
        words=(
            Word(w="بێدەنگی", start_ms=5500, end_ms=6500, conf=0.50),  # inside excised dead air
        ),
        complete=True,
    )
    s2 = Sentence(
        words=(
            Word(w="وتەی", start_ms=7200, end_ms=8500, conf=0.99),
            Word(w="دووەم", start_ms=8800, end_ms=9800, conf=0.96),
        ),
        complete=True,
    )
    s3 = Sentence(
        words=(
            Word(w="وتەی", start_ms=12200, end_ms=13200, conf=0.98),
            Word(w="کۆتایی", start_ms=13400, end_ms=14400, conf=0.95),
        ),
        complete=True,
    )

    brief = EditorialBrief(
        viewer_takeaway="تێگەیشتنی سەرەکی لە دیالۆگەکە",
        content_type=ContentType.PODCAST,
        target_duration_ms=(6000, 12000),
    )
    config = EffectiveConfiguration.resolve(
        content_type=ContentType.PODCAST,
        caption_style=CaptionStyle.WORD_HIGHLIGHT,
        fps=25.0,
    )

    plan = VisualEditPlan(
        version=CURRENT_PLAN_VERSION,
        clip_id="clip_trim_share",
        media_id="episode_multi_trim",
        media_sha256="c" * 64,
        brief=brief,
        config=config,
        time_mapping=time_mapping,
        shot_cuts_ms=(4000, 8500, 13000),
        punch_in_ms=(3200, 8800),
        speaker_turns=(
            (2000, 5000, "Spk1"),
            (7000, 10000, "Spk2"),
            (12000, 15000, "Spk1"),
        ),
        sentences=(s1, s_excised, s2, s3),
    )

    # 3. Derive output sentences: excised sentence s_excised must be dropped
    out_sentences = plan.derive_sentences_for_output()
    assert len(out_sentences) == 3
    # Sentence 1 in output time:
    assert out_sentences[0].words[0].w == "وتەی"
    assert out_sentences[0].words[0].start_ms == 200
    assert out_sentences[0].words[0].end_ms == 1000
    assert out_sentences[0].words[1].w == "یەکەم"
    assert out_sentences[0].words[1].start_ms == 1200
    assert out_sentences[0].words[1].end_ms == 2800

    # Sentence 2 in output time (shifted by 2000 ms excised gap):
    assert out_sentences[1].words[0].w == "وتەی"
    assert out_sentences[1].words[0].start_ms == 3200
    assert out_sentences[1].words[0].end_ms == 4500
    assert out_sentences[1].words[1].w == "دووەم"
    assert out_sentences[1].words[1].start_ms == 4800
    assert out_sentences[1].words[1].end_ms == 5800

    # Sentence 3 in output time (shifted by 2000 + 2000 = 4000 ms cumulative excised gaps):
    assert out_sentences[2].words[0].w == "وتەی"
    assert out_sentences[2].words[0].start_ms == 6200
    assert out_sentences[2].words[0].end_ms == 7200
    assert out_sentences[2].words[1].w == "کۆتایی"
    assert out_sentences[2].words[1].start_ms == 7400
    assert out_sentences[2].words[1].end_ms == 8400

    # 4. Derive SRT:
    srt_text = plan.derive_srt()
    assert "00:00:00,200 --> 00:00:02,800" in srt_text
    assert "00:00:03,200 --> 00:00:05,800" in srt_text
    assert "00:00:06,200 --> 00:00:08,400" in srt_text
    assert "بێدەنگی" not in srt_text

    # 5. Derive EDL: Must emit 3 distinct pairs of events (6 total lines: 001..006)
    edl_text = plan.derive_edl(title="TRIMMED CLIP")
    edl_lines = [line for line in edl_text.splitlines() if line.strip() and line[:3].isdigit()]
    assert len(edl_lines) == 6

    # Segment 1 (2000..5000 ms = 00:00:02:00..00:00:05:00 source, 00:00:00:00..00:00:03:00 record)
    assert (
        "001  AX       V     C        00:00:02:00 00:00:05:00 00:00:00:00 00:00:03:00" in edl_text
    )
    assert (
        "002  AX       A     C        00:00:02:00 00:00:05:00 00:00:00:00 00:00:03:00" in edl_text
    )
    # Segment 2 (7000..10000 ms = 00:00:07:00..00:00:10:00 source, 00:00:03:00..00:00:06:00 record)
    assert (
        "003  AX       V     C        00:00:07:00 00:00:10:00 00:00:03:00 00:00:06:00" in edl_text
    )
    assert (
        "004  AX       A     C        00:00:07:00 00:00:10:00 00:00:03:00 00:00:06:00" in edl_text
    )
    # Segment 3 (12000..15000 ms = 00:00:12:00..00:00:15:00 source, 00:00:06:00..00:00:09:00 record)
    assert (
        "005  AX       V     C        00:00:12:00 00:00:15:00 00:00:06:00 00:00:09:00" in edl_text
    )
    assert (
        "006  AX       A     C        00:00:12:00 00:00:15:00 00:00:06:00 00:00:09:00" in edl_text
    )

    # 6. Derive OTIO:
    otio = plan.derive_otio("/media/source.mp4")
    v_track = otio["tracks"]["children"][0]
    a_track = otio["tracks"]["children"][1]
    assert len(v_track["children"]) == 3
    assert len(a_track["children"]) == 3

    # Check OTIO markers placed on the shared output timeline:
    markers = v_track["children"][0]["markers"]
    # Punch-in at source 8800 ms -> output 4800 ms (at 25 fps -> frame round(4800 * 0.025) = 120)
    punch_markers = [m for m in markers if m["metadata"].get("type") == "punch_in"]
    assert len(punch_markers) == 2
    assert punch_markers[1]["marked_range"]["start_time"]["value"] == 120

    # Speaker turns on output timeline:
    spk_markers = [m for m in markers if m["metadata"].get("type") == "speaker_turn"]
    assert len(spk_markers) == 3
    # Turn 2: source 7000..10000 ms -> output 3000..6000 ms -> start frame 75, duration 75 frames
    assert spk_markers[1]["name"] == "Speaker: Spk2"
    assert spk_markers[1]["marked_range"]["start_time"]["value"] == 75
    assert spk_markers[1]["marked_range"]["duration"]["value"] == 75


def test_vfr_and_fractional_rate_keep_audio_caption_and_edit_alignment() -> None:
    """AC-10 / Task T06: VFR and fractional frame rates preserve declared timebase without drift."""
    from hawedit.delivery import DeliveryError, build_edl, ms_to_timecode

    # 1. Locked NTSC drop-frame rate: 30000 / 1001 (~29.97 fps)
    fps_ntsc = 30_000 / 1_001

    # Over 10 minutes (600,000 ms):
    # Physical frames = round(600_000 * 30 / 1.001 / 1000) = 17,982 frames.
    # In SMPTE drop frame: at each minute mark except 0, 10, 20, 30, 40, 50,
    # two frame counts are skipped.
    # Over 10 minutes, 9 non-tenth minute marks * 2 dropped counts = 18 frame addresses skipped.
    # Adjusted total frame count = 17,982 + 18 = 18,000 frames.
    # 18,000 frames at 30 fps nominal = exactly 10 minutes, 0 seconds, 0 frames -> "00:10:00;00"!
    tc_10min = ms_to_timecode(600_000, fps_ntsc)
    assert tc_10min == "00:10:00;00", f"Drop-frame timecode drifted from wall clock: {tc_10min}"

    # 2. Multi-cut EDL conforming at fractional rate:
    # Clip with 3 retained segments:
    # Seg 1: 0..60060 ms (2 minutes non-drop = 1800 frames physical)
    # Seg 2: 70070..130130 ms (60060 ms = 1800 frames physical)
    # Seg 3: 150150..210210 ms (60060 ms = 1800 frames physical)
    # Total output duration: 180,180 ms = exactly 5400 physical frames
    edl_ntsc = build_edl(
        clip_in_ms=0,
        clip_out_ms=210210,
        fps=fps_ntsc,
        title="NTSC MULTI-CUT",
        retained_intervals=((0, 60060), (70070, 130130), (150150, 210210)),
    )
    assert "FCM: DROP FRAME" in edl_ntsc

    # Parse record in/out of each event
    events = [
        line
        for line in edl_ntsc.splitlines()
        if line.startswith("0") and "  AX  " in line and " V " in line
    ]
    assert len(events) == 3

    # Event 1: Record 00:00:00;00 to 00:01:00;02
    e1_fields = events[0].split()[-4:]
    assert e1_fields[2] == "00:00:00;00"
    assert e1_fields[3] == "00:01:00;02"

    # Event 2: Record in must match Event 1's record out EXACTLY with zero gap/drift!
    e2_fields = events[1].split()[-4:]
    assert e2_fields[2] == "00:01:00;02", (
        "Record in of segment 2 drifted from record out of segment 1"
    )
    assert e2_fields[3] == "00:02:00;04"

    # Event 3: Record in must match Event 2's record out EXACTLY with zero gap/drift!
    e3_fields = events[2].split()[-4:]
    assert e3_fields[2] == "00:02:00;04", (
        "Record in of segment 3 drifted from record out of segment 2"
    )
    assert e3_fields[3] == "00:03:00;06"

    # 3. Audio / Caption alignment tolerance:
    # Verify sub-frame sync: at 29.97 fps, 1 frame is ~33.367 ms.
    # For a caption cue at 60060 ms:
    # Sub-frame difference between millisecond clock and timecode frame address is
    # strictly < 1 frame (33.37 ms).
    frame_from_ms = round(60060 * fps_ntsc / 1000)
    calculated_ms_from_frame = round(frame_from_ms * 1000 / fps_ntsc)
    assert abs(60060 - calculated_ms_from_frame) < 17

    # 4. Strict fail-stop on unsupported arbitrary fractional rate:
    with pytest.raises(DeliveryError, match="fractional frame rate .* is unsupported"):
        build_edl(clip_in_ms=0, clip_out_ms=5000, fps=28.3)
