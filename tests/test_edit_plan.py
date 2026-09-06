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
