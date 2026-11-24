"""Tests for E3 hard edit rules (`validate_edl`), silence padding, and wired render_critic."""

from __future__ import annotations

from pathlib import Path

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
from hawedit.render_critic import (
    RenderedSequenceContext,
    UnsupportedAllClearError,
    inspect_rendered_sequence,
)
from hawedit.sentences import Sentence
from hawedit.silence import plan_silence_tightening
from hawedit.transcripts import AsrProvenance, RawTranscript, Word

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"


def _word(text: str, start_ms: int, end_ms: int, conf: float = 0.95) -> Word:
    return Word(w=text, start_ms=start_ms, end_ms=end_ms, conf=conf)


def _make_plan(
    *,
    clip_in_ms: int,
    clip_out_ms: int,
    retained_intervals_ms: tuple[tuple[int, int], ...],
    words: tuple[Word, ...],
    content_type: ContentType = ContentType.PODCAST,
) -> VisualEditPlan:
    dur = sum(e - s for s, e in retained_intervals_ms)
    return VisualEditPlan(
        version=CURRENT_PLAN_VERSION,
        clip_id="clip-test-01",
        media_id="media_test",
        media_sha256="a" * 64,
        brief=EditorialBrief(
            viewer_takeaway="Kurdish editorial test point",
            content_type=content_type,
            target_duration_ms=(max(1, min(30_000, dur)), max(30_000, dur)),
        ),
        config=EffectiveConfiguration.resolve(
            content_type=content_type, caption_style=CaptionStyle.WORD_HIGHLIGHT
        ),
        time_mapping=SourceTimeMapping(
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            retained_intervals_ms=retained_intervals_ms,
        ),
        sentences=(Sentence(words=words, complete=True),),
    )


def test_validate_edl_rejects_outer_cut_inside_word() -> None:
    from hawedit.edit_plan import EditRuleViolationError, validate_edl

    words = (
        _word("سڵاو", 1000, 1800),
        _word("هاوڕێیان.", 2000, 35000),
    )
    # Start cut at 1400 falls strictly inside word "سڵاو" (1000..1800).
    plan = _make_plan(
        clip_in_ms=1400,
        clip_out_ms=35100,
        retained_intervals_ms=((1400, 35100),),
        words=words,
    )
    with pytest.raises(EditRuleViolationError, match="splits word"):
        validate_edl(plan, words=words)


def test_validate_edl_rejects_internal_splice_inside_word() -> None:
    from hawedit.edit_plan import EditRuleViolationError, validate_edl

    words = (
        _word("سڵاو", 1000, 2000),
        _word("کوردستان", 2500, 4000),
        _word("ئارامە.", 4500, 35000),
    )
    # Internal splice ends seg0 at 3000 inside "کوردستان" (2500..4000).
    plan = _make_plan(
        clip_in_ms=900,
        clip_out_ms=35100,
        retained_intervals_ms=((900, 3000), (4400, 35100)),
        words=words,
    )
    with pytest.raises(EditRuleViolationError, match="splits word"):
        validate_edl(plan, words=words)


def test_validate_edl_rejects_under_padded_cut_below_30ms() -> None:
    from hawedit.edit_plan import EditRuleViolationError, validate_edl

    words = (
        _word("سڵاو", 1000, 1500),
        _word("هاوڕێیان.", 1600, 35000),
    )
    # Start cut is at 985 -> only 15 ms before first word (< 30 ms).
    plan = _make_plan(
        clip_in_ms=985,
        clip_out_ms=35100,
        retained_intervals_ms=((985, 35100),),
        words=words,
    )
    with pytest.raises(EditRuleViolationError, match="padding"):
        validate_edl(plan, words=words)


def test_validate_edl_rejects_over_padded_cut_above_200ms() -> None:
    from hawedit.edit_plan import EditRuleViolationError, validate_edl

    words = (
        _word("سڵاو", 1000, 1500),
        _word("هاوڕێیان.", 1600, 35000),
    )
    # Tail extends to 35350 -> 350 ms padding after last word (> 200 ms).
    plan = _make_plan(
        clip_in_ms=900,
        clip_out_ms=35350,
        retained_intervals_ms=((900, 35350),),
        words=words,
    )
    with pytest.raises(EditRuleViolationError, match="padding"):
        validate_edl(plan, words=words)


def test_validate_edl_accepts_boundaries_within_30_to_200ms() -> None:
    from hawedit.edit_plan import EditRuleViolationError, validate_edl

    words = (
        _word("دەستپێک", 1000, 1800),
        _word("کۆتایی.", 4000, 36000),
    )
    # Outer: 100 ms before 1000, 100 ms after 36000; internal splice keeps 75 ms both sides.
    plan = _make_plan(
        clip_in_ms=900,
        clip_out_ms=36100,
        retained_intervals_ms=((900, 1875), (3925, 36100)),
        words=words,
    )
    result = validate_edl(plan, words=words)
    assert result.is_valid is True
    assert result.violations == ()

    # Physical 0 / media_duration_ms clamps pass when no unselected word sits < 30 ms outside.
    clamped_words = (_word("یەکەم", 10, 500), _word("کۆتایی.", 500, 34990))
    clamped_plan = _make_plan(
        clip_in_ms=0,
        clip_out_ms=35000,
        retained_intervals_ms=((0, 35000),),
        words=clamped_words,
    )
    clamped_res = validate_edl(clamped_plan, words=clamped_words, media_duration_ms=35000)
    assert clamped_res.is_valid is True

    # Fail-stop when an unselected adjacent word sits < 30 ms outside an outer edge.
    all_words = (_word("پێش", 700, 890), *words)  # 900 - 890 = 10 ms < 30 ms!
    with pytest.raises(EditRuleViolationError, match="unselected"):
        validate_edl(plan, words=words, all_words=all_words)


def test_validate_edl_rejects_duration_below_min_bound() -> None:
    from hawedit.edit_plan import EditRuleViolationError, validate_edl

    words = (_word("کورت", 1000, 20000),)
    plan = _make_plan(
        clip_in_ms=900,
        clip_out_ms=20100,
        retained_intervals_ms=((900, 20100),),
        words=words,
    )
    with pytest.raises(EditRuleViolationError, match="duration"):
        validate_edl(plan, words=words)  # Default min is 30_000 ms


def test_validate_edl_rejects_duration_above_max_bound() -> None:
    from hawedit.edit_plan import EditRuleViolationError, validate_edl

    # 70 s passes default 30-90 s, fails "social" preset 30-55 s; 95 s fails default 30-90 s.
    words_70s = (_word("مامناوەند", 1000, 70000),)
    plan_70s = _make_plan(
        clip_in_ms=900,
        clip_out_ms=70100,
        retained_intervals_ms=((900, 70100),),
        words=words_70s,
    )
    assert validate_edl(plan_70s, words=words_70s).is_valid is True
    with pytest.raises(EditRuleViolationError, match="duration"):
        validate_edl(plan_70s, words=words_70s, duration_preset="social")

    words_95s = (_word("درێژ", 1000, 95000),)
    plan_95s = _make_plan(
        clip_in_ms=900,
        clip_out_ms=95100,
        retained_intervals_ms=((900, 95100),),
        words=words_95s,
    )
    with pytest.raises(EditRuleViolationError, match="duration"):
        validate_edl(plan_95s, words=words_95s)


def test_plan_silence_tightening_keeps_at_least_30ms_padding_on_both_sides() -> None:
    from hawedit.edit_plan import validate_edl

    words = (
        _word("سلێمانی", 1000, 2000),
        _word("جووانە.", 3500, 35000),
    )
    plan = plan_silence_tightening(
        words,
        clip_in_ms=900,
        clip_out_ms=35100,
        threshold_ms=600,
        target_gap_ms=150,
    )
    assert len(plan.retained_intervals_ms) == 2
    seg0_end_src = 900 + plan.retained_intervals_ms[0][1]
    seg1_start_src = 900 + plan.retained_intervals_ms[1][0]
    assert 30 <= (seg0_end_src - 2000) <= 200
    assert 30 <= (3500 - seg1_start_src) <= 200

    abs_retained = tuple((900 + s, 900 + e) for s, e in plan.retained_intervals_ms)
    edl_plan = _make_plan(
        clip_in_ms=900,
        clip_out_ms=35100,
        retained_intervals_ms=abs_retained,
        words=words,
    )
    # 35100 - 900 - 1350 = 32850 ms >= 30_000 ms, both cut margins = 75 ms -> strictly valid!
    assert validate_edl(edl_plan, words=words).is_valid is True


def test_pipeline_aborts_before_render_when_validate_edl_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hashlib

    from hawedit.clip import Qc
    from hawedit.judge import KURDISH_EDITORIAL_JUDGE, JudgeVerdict
    from hawedit.pipeline import StageSkipped, run_pipeline

    render_calls = 0

    def counting_render_clip(*args: object, **kwargs: object) -> object:
        nonlocal render_calls
        render_calls += 1
        raise AssertionError("render_clip must not be called when validate_edl rejects")

    monkeypatch.setattr("hawedit.pipeline.render_clip", counting_render_clip)

    fixture_sha = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    # Words span 100..1700 ms (1900 ms total); min_clip_ms=3000 applies (< 4162 ms source).
    words = (
        _word("ڕۆژنامەوانی", 100, 800),
        _word("کوردی.", 800, 1700),
        _word("لە", 2000, 2400),
        _word("هەولێر.", 2400, 4100),
    )
    transcript = RawTranscript(
        media_id="edl_gate",
        text_ckb="ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=words,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=fixture_sha,
    )
    verdict = JudgeVerdict(
        candidate_id="edl-gate-0",
        clip_in_ms=100,
        clip_out_ms=1700,
        hook_score=0.9,
        self_contained=True,
        meaning_fidelity=0.95,
        misleading_edit_risk=0.02,
        cultural_landing=0.9,
        title_ckb="تێست",
        description_ckb="وەسف",
        hashtags_ckb=("#کوردی",),
        payoff_at_ms=1500,
        narrative_role="payoff",
        judge=KURDISH_EDITORIAL_JUDGE,
    )

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="edl_gate",
        transcript=transcript,
        select_sentences=(0,),
        min_clip_ms=3_000,
        verdict=verdict,
        qc=Qc(auto_pass=True),
    )
    assert render_calls == 0
    assert isinstance(run.render, StageSkipped)


def test_render_critic_rejects_claim_all_clear_on_edit_rule_violation() -> None:
    words = (_word("سڵاو", 100, 800), _word("کوردی.", 800, 1700))
    # Invalid cut right at word boundary inside "کوردی." (1200 inside 800..1700).
    bad_plan = _make_plan(
        clip_in_ms=0,
        clip_out_ms=1200,
        retained_intervals_ms=((0, 1200),),
        words=words,
    )
    ctx = RenderedSequenceContext(
        render_path=FIXTURE,
        duration_ms=4162,
        fps=25.0,
        edit_plan=bad_plan,
        edl_words=words,
        edl_min_duration_ms=0,
        edl_max_duration_ms=90_000,
    )
    result = inspect_rendered_sequence(ctx, claim_all_clear=True)
    assert result.is_all_clear is False
    assert result.all_clear_refused is True
    assert result.has_critical_defects is True
    with pytest.raises(UnsupportedAllClearError):
        result.assert_verdict_grounded()


def test_render_critic_samples_multi_frame_temporal_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cv2

    seek_positions: list[float] = []
    real_capture = cv2.VideoCapture

    class TrackingCapture:
        def __init__(self, path: str) -> None:
            self._inner = real_capture(path)

        def isOpened(self) -> bool:
            return bool(self._inner.isOpened())

        def get(self, prop_id: int) -> float:
            return float(self._inner.get(prop_id))

        def set(self, prop_id: int, value: float) -> bool:
            if prop_id == cv2.CAP_PROP_POS_MSEC:
                seek_positions.append(float(value))
            return bool(self._inner.set(prop_id, value))

        def read(self) -> tuple[bool, object]:
            return self._inner.read()

        def release(self) -> None:
            self._inner.release()

    monkeypatch.setattr(cv2, "VideoCapture", TrackingCapture)
    ctx = RenderedSequenceContext(
        render_path=FIXTURE,
        duration_ms=4162,
        fps=25.0,
    )
    result = inspect_rendered_sequence(ctx, claim_all_clear=False)
    assert result.observed_media is True
    assert len(result.windows) >= 2
    assert all(w.is_observed and w.frame_count >= 2 for w in result.windows)
    # Multi-frame Check #0 must sample >= 2 distinct timestamps per temporal window.
    assert len(seek_positions) >= 2 * len(result.windows)


def test_pipeline_edl_padding_bounds_keeps_30_to_200_on_unaligned_and_bounded_runs() -> None:
    from hawedit.edit_plan import MAX_STAGE5_SIGNAL_EXTENSION_MS, pipeline_edl_padding_bounds

    # Unaligned Stage 5 tail / None keep strict 30..200 ms even when silence target < 60.
    min_pad, max_in, max_out = pipeline_edl_padding_bounds(
        in_extended_by=None,
        out_extended_by="tail",
        shot_cut_window_ms=400,
        silence_threshold_ms=200,
        silence_target_gap_ms=5,
        min_duration_ms=30_000,
    )
    assert (min_pad, max_in, max_out) == (30, 200, 200)

    # Shot cuts allow up to shot_cut_window_ms (400 ms); natural_silence/speaker_turn allow 600 ms.
    min_sc, max_in_sc, max_out_sc = pipeline_edl_padding_bounds(
        in_extended_by="shot_cut",
        out_extended_by="natural_silence",
        shot_cut_window_ms=400,
        silence_threshold_ms=0,
        silence_target_gap_ms=150,
        min_duration_ms=30_000,
    )
    assert (min_sc, max_in_sc, max_out_sc) == (30, 400, MAX_STAGE5_SIGNAL_EXTENSION_MS)

    min_s5, max_in_s5, max_out_s5 = pipeline_edl_padding_bounds(
        in_extended_by="vad_onset",
        out_extended_by="speaker_turn_end",
        shot_cut_window_ms=400,
        silence_threshold_ms=0,
        silence_target_gap_ms=150,
        min_duration_ms=30_000,
    )
    assert (min_s5, max_in_s5, max_out_s5) == (
        30,
        MAX_STAGE5_SIGNAL_EXTENSION_MS,
        MAX_STAGE5_SIGNAL_EXTENSION_MS,
    )
