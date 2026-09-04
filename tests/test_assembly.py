"""Unit tests for Multi-Moment Story Assembly (pro-edit T6, AC-7, AC-8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.assembly import (
    assemble_cold_open,
    assemble_spans,
    assembled_splice_filter,
    judge_assembled_reel_multimodal,
    judge_assembly,
    render_assembled_reel,
)
from hawedit.captions import find_ffmpeg
from hawedit.clip import EditorialBelowThreshold
from hawedit.judge import InputMode, JudgeRequest, JudgeVerdict
from hawedit.sentences import Sentence
from hawedit.transcripts import Word

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"
FONTS = ROOT / "assets" / "fonts"


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


def test_assemble_cold_open_orders_payoff_first_and_shifts_timings() -> None:
    """Task T4.9: Cold-open assembly puts payoff sentence first and shifts setup after it."""
    # Setup sentence from earlier: 0 to 1,500ms
    setup_sent = _make_sentence([("ئەمە", 0, 700), ("پێشەکییە", 800, 1_500)])
    # Payoff sentence from climax: 20,000 to 22,000ms (duration 2,000ms)
    payoff_sent = _make_sentence([("ئەمە", 20_000, 20_800), ("ئەنجامەکەیە", 21_000, 22_000)])

    reel = assemble_cold_open([setup_sent], payoff_sent)

    assert len(reel.spans) == 2
    assert reel.total_duration_ms == 3_500  # 2000ms + 1500ms

    # Span 0: Payoff sentence (first)
    assert reel.spans[0].source_in_ms == 20_000
    assert reel.spans[0].source_out_ms == 22_000
    assert reel.assembled_sentences[0].words[0].w == "ئەمە"
    assert reel.assembled_sentences[0].words[0].start_ms == 0
    assert reel.assembled_sentences[0].words[1].w == "ئەنجامەکەیە"
    assert reel.assembled_sentences[0].words[1].end_ms == 2_000

    # Span 1: Setup sentence (second, shifted after payoff)
    assert reel.spans[1].source_in_ms == 0
    assert reel.spans[1].source_out_ms == 1_500
    assert reel.assembled_sentences[1].words[0].w == "ئەمە"
    assert reel.assembled_sentences[1].words[0].start_ms == 2_000
    assert reel.assembled_sentences[1].words[1].w == "پێشەکییە"
    assert reel.assembled_sentences[1].words[1].end_ms == 3_500


def test_assembled_splice_filter_constructs_trim_and_concat() -> None:
    """Task T4.9: assembled_splice_filter builds valid trim/atrim/concat filtergraph."""
    setup = _make_sentence([("دەستپێک", 0, 1_000)])
    payoff = _make_sentence([("کۆتایی", 10_000, 12_000)])
    reel = assemble_cold_open([setup], payoff)

    filter_str = assembled_splice_filter(reel.spans)
    assert "[0:v]trim=start=10.000:end=12.000,setpts=PTS-STARTPTS[v0]" in filter_str
    assert "[0:a]atrim=start=10.000:end=12.000,asetpts=PTS-STARTPTS[a0]" in filter_str
    assert "[0:v]trim=start=0.000:end=1.000,setpts=PTS-STARTPTS[v1]" in filter_str
    assert "[0:a]atrim=start=0.000:end=1.000,asetpts=PTS-STARTPTS[a1]" in filter_str
    assert "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v_concat][a_concat]" in filter_str


def test_an_assembled_reel_is_rendered_and_judged_with_its_own_frames(tmp_path: Path) -> None:
    """Proof A: Cold-open assembly renders physical 9:16 media and judges with extracted frames."""
    if find_ffmpeg() is None:
        pytest.skip("ffmpeg required for cold-open assembly render test")

    # Use real fixture: 4162 ms duration
    # Payoff span: 2,000ms to 3,200ms (duration 1,200ms)
    payoff_sent = _make_sentence([("ئەنجامی", 2_000, 2_500), ("گرنگ", 2_600, 3_200)])
    # Setup span: 200ms to 1,200ms (duration 1,000ms)
    setup_sent = _make_sentence([("دەستپێکی", 200, 600), ("باسەکە", 700, 1_200)])

    reel = assemble_cold_open([setup_sent], payoff_sent)
    assert reel.total_duration_ms == 2_200

    out_mp4 = tmp_path / "cold_open_assembled.mp4"
    work_dir = tmp_path / "work"

    # Re-timed punch-in on the boundary between cold open and setup (at t=1200ms)
    punch_ins = ((1_200, 1.15),)

    render_assembled_reel(
        reel=reel,
        source_video_path=FIXTURE,
        output_path=out_mp4,
        work_dir=work_dir,
        source_width=640,
        source_height=360,
        punch_ins=punch_ins,
        fonts_dir=FONTS,
    )

    assert out_mp4.is_file()
    assert out_mp4.stat().st_size > 0

    judge = MockEditorialJudge(hook_score=0.91, misleading_edit_risk=0.03)
    verdict = judge_assembled_reel_multimodal(
        reel=reel,
        rendered_mp4_path=out_mp4,
        judge=judge,
        work_dir=work_dir,
        frame_count=3,
    )

    assert verdict.hook_score == 0.91
    assert verdict.misleading_edit_risk == 0.03
    assert len(judge.recorded_requests) == 1

    req = judge.recorded_requests[0]
    assert req.mode == InputMode.STAGE_4_WITH_VIDEO
    assert len(req.keyframes) == 3
    for frame in req.keyframes:
        assert frame.mime_type == "image/jpeg"
        assert len(frame.data) > 0


def test_judge_assembled_reel_multimodal_refuses_misleading_assembly(tmp_path: Path) -> None:
    """Task T4.9: Assembled reel exceeding misleading_edit_risk > 0.10 is refused."""
    if find_ffmpeg() is None:
        pytest.skip("ffmpeg required for cold-open assembly render test")

    payoff_sent = _make_sentence([("ئەنجامی", 2_000, 3_000)])
    setup_sent = _make_sentence([("دەستپێک", 200, 1_000)])
    reel = assemble_cold_open([setup_sent], payoff_sent)

    out_mp4 = tmp_path / "misleading.mp4"
    work_dir = tmp_path / "work"

    render_assembled_reel(
        reel=reel,
        source_video_path=FIXTURE,
        output_path=out_mp4,
        work_dir=work_dir,
        source_width=640,
        source_height=360,
        fonts_dir=FONTS,
    )

    risky_judge = MockEditorialJudge(hook_score=0.90, misleading_edit_risk=0.18)
    with pytest.raises(EditorialBelowThreshold, match="misleading edit risk 0.18 > 0.10"):
        judge_assembled_reel_multimodal(
            reel=reel,
            rendered_mp4_path=out_mp4,
            judge=risky_judge,
            work_dir=work_dir,
            frame_count=2,
        )
