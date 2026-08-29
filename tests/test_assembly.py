"""Unit tests for Multi-Moment Story Assembly (pro-edit T6, AC-7, AC-8)."""

from __future__ import annotations

import pytest

from hawedit.assembly import assemble_spans, judge_assembly
from hawedit.clip import EditorialBelowThreshold
from hawedit.judge import JudgeRequest, JudgeVerdict
from hawedit.sentences import Sentence
from hawedit.transcripts import Word


class MockEditorialJudge:
    """Mock editorial judge for testing assembly scoring."""

    model_id: str = "gemini-2.5-pro"

    def __init__(
        self,
        *,
        hook_score: float = 0.85,
        misleading_edit_risk: float = 0.08,
        self_contained: bool = True,
        meaning_fidelity: float = 1.0,
    ) -> None:
        self.hook_score = hook_score
        self.misleading_edit_risk = misleading_edit_risk
        self.self_contained = self_contained
        self.meaning_fidelity = meaning_fidelity
        self.recorded_requests: list[JudgeRequest] = []

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        self.recorded_requests.append(request)
        return JudgeVerdict(
            candidate_id=request.candidate_id,
            hook_score=self.hook_score,
            self_contained=self.self_contained,
            payoff_at_ms=request.clip_out_ms // 2,
            meaning_fidelity=self.meaning_fidelity,
            misleading_edit_risk=self.misleading_edit_risk,
            cultural_landing=0.95,
            narrative_role="payoff",
            title_ckb="کوردستان و سەقامگیری",
            description_ckb="باسێک لەسەر گرنگی سەقامگیری لە هەرێمی کوردستان.",
            hashtags_ckb=("#کوردستان", "#ئاسایش"),
            judge=self.model_id,
            clip_in_ms=request.clip_in_ms,
            clip_out_ms=request.clip_out_ms,
        )


def _make_sentence(words_with_times: list[tuple[str, int, int]], complete: bool = True) -> Sentence:
    words = tuple(
        Word(w=w, start_ms=start, end_ms=end, conf=0.95) for w, start, end in words_with_times
    )
    return Sentence(words=words, complete=complete)


def test_word_timings_shift_correctly_across_assembled_spans() -> None:
    """Test that words in non-contiguous spans shift onto continuous timeline starting at 0."""
    # Span 1: 10,000ms to 12,000ms (duration 2,000ms)
    span1_sent = _make_sentence([("ئەمە", 10_000, 10_800), ("سەرەتایە", 11_000, 12_000)])

    # Span 2: 50,000ms to 53,000ms (duration 3,000ms)
    span2_sent = _make_sentence([("ئەمەش", 50_000, 51_200), ("کۆتاییەکەیە", 51_500, 53_000)])

    reel = assemble_spans([[span1_sent], [span2_sent]])

    assert len(reel.spans) == 2
    assert reel.total_duration_ms == 5_000  # 2000ms + 3000ms

    # Span 1 check: should start at 0ms
    assert reel.assembled_sentences[0].words[0].start_ms == 0
    assert reel.assembled_sentences[0].words[0].end_ms == 800
    assert reel.assembled_sentences[0].words[1].start_ms == 1_000
    assert reel.assembled_sentences[0].words[1].end_ms == 2_000

    # Span 2 check: should start at 2,000ms (shifted by span 1's duration)
    assert reel.assembled_sentences[1].words[0].start_ms == 2_000
    assert reel.assembled_sentences[1].words[0].end_ms == 3_200
    assert reel.assembled_sentences[1].words[1].start_ms == 3_500
    assert reel.assembled_sentences[1].words[1].end_ms == 5_000


def test_an_assembled_reel_is_judged_as_one() -> None:
    """AC-7: When several moments are assembled into one reel, the judge scores as one unit."""
    span1 = [_make_sentence([("هۆکاری", 1_000, 2_000), ("سەرەکی", 2_200, 3_500)])]
    span2 = [_make_sentence([("ئاسایشە", 20_000, 21_500), ("لێرەدا", 21_800, 23_000)])]

    reel = assemble_spans([span1, span2])
    judge = MockEditorialJudge(hook_score=0.88, misleading_edit_risk=0.05)

    _ = judge_assembly(reel, judge)

    assert len(judge.recorded_requests) == 1
    req = judge.recorded_requests[0]
    # Request text contains words from BOTH spans combined
    assert "هۆکاری" in req.text_ckb and "ئاسایشە" in req.text_ckb
    assert req.clip_in_ms == 0
    assert req.clip_out_ms == reel.total_duration_ms


def test_the_verdict_is_recorded_against_the_assembly() -> None:
    """AC-7: The verdict is recorded against the assembly identifier, not source spans."""
    span1 = [_make_sentence([("پرسیار", 5_000, 7_000)])]
    span2 = [_make_sentence([("وەڵام", 40_000, 42_000)])]

    reel = assemble_spans([span1, span2])
    judge = MockEditorialJudge()

    verdict = judge_assembly(reel, judge)

    assert verdict.candidate_id.startswith("assembly-2spans-")
    assert verdict.clip_in_ms == 0
    assert verdict.clip_out_ms == 4_000


def test_editorial_thresholds_apply_to_the_assembly() -> None:
    """AC-8: When an assembled reel is scored, the §2 editorial thresholds apply."""
    span1 = [_make_sentence([("وتارێک", 1_000, 3_000)])]
    span2 = [_make_sentence([("پەیامێک", 10_000, 12_000)])]
    reel = assemble_spans([span1, span2])

    # 1. Failing hook score (< 0.75)
    low_hook_judge = MockEditorialJudge(hook_score=0.60)
    with pytest.raises(EditorialBelowThreshold, match="hook score 0.60 < 0.75"):
        judge_assembly(reel, low_hook_judge)

    # 2. Excessive misleading edit risk (> 0.10)
    risky_judge = MockEditorialJudge(misleading_edit_risk=0.15)
    with pytest.raises(EditorialBelowThreshold, match="misleading edit risk 0.15 > 0.10"):
        judge_assembly(reel, risky_judge)

    # 3. Not self-contained
    uncontained_judge = MockEditorialJudge(self_contained=False)
    with pytest.raises(EditorialBelowThreshold, match="not self-contained"):
        judge_assembly(reel, uncontained_judge)

    # 4. Low meaning fidelity (< 1.0)
    low_fidelity_judge = MockEditorialJudge(meaning_fidelity=0.90)
    with pytest.raises(EditorialBelowThreshold, match="meaning fidelity 0.90 is below 1.00"):
        judge_assembly(reel, low_fidelity_judge)


def test_incomplete_sentences_are_refused_under_invariant_two() -> None:
    """Kurdish invariant #2: Incomplete sentence in any span must refuse assembly."""
    good_span = [_make_sentence([("باش", 1_000, 2_000)], complete=True)]
    incomplete_span = [_make_sentence([("نیوەچڵ", 5_000, 6_000)], complete=False)]

    with pytest.raises(ValueError, match="invariant #2 violation"):
        assemble_spans([good_span, incomplete_span])


def test_empty_or_invalid_spans_are_refused() -> None:
    """Empty span groups or invalid timings are rejected immediately."""
    with pytest.raises(ValueError, match="empty sequence"):
        assemble_spans([])

    with pytest.raises(ValueError, match="Span group 0 is empty"):
        assemble_spans([[]])
