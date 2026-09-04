"""Tests for run cost accounting (T0.6).

Every billed call records model, counted tokens, USD estimate (labelled so),
in the run report and events. Sum per run.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.clip import DiscoveryPath
from hawedit.discovery import Candidate
from hawedit.events import JsonlEventSink, RunEvent, RunEventLog, RunState, read_events
from hawedit.judge import (
    BilledCall,
    JudgeRequest,
    JudgeVerdict,
    estimate_cost_usd,
)
from hawedit.pipeline import _print_report, run_pipeline
from hawedit.transcripts import AsrProvenance, RawTranscript, Word

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"
FIXTURE_SHA256 = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")

WORDS = (
    Word(w="ڕۆژنامەوانی", start_ms=100, end_ms=800, conf=0.95),
    Word(w="کوردی.", start_ms=800, end_ms=1_700, conf=0.94),
    Word(w="لە", start_ms=2_000, end_ms=2_400, conf=0.93),
    Word(w="هەولێر.", start_ms=2_400, end_ms=4_100, conf=0.92),
)


def a_transcript(media_id: str = "kurdish-speech-3cuts") -> RawTranscript:
    return RawTranscript(
        media_id=media_id,
        text_ckb="ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=WORDS,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=FIXTURE_SHA256,
    )


def a_verdict(clip_in_ms: int, clip_out_ms: int) -> JudgeVerdict:
    return JudgeVerdict(
        candidate_id="kurdish-speech-3cuts-0",
        hook_score=0.85,
        self_contained=True,
        payoff_at_ms=(clip_in_ms + clip_out_ms) // 2,
        meaning_fidelity=0.95,
        misleading_edit_risk=0.02,
        cultural_landing=0.90,
        narrative_role="payoff",
        title_ckb="ڕۆژنامەوانی کوردی لە هەولێر",
        description_ckb="بابەتێکی گرنگ دەربارەی ڕۆژنامەوانی",
        hashtags_ckb=("#کوردی",),
        judge="gemini-2.5-pro",
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
    )


class MockPathADiscoverer:
    def __init__(self, candidates: tuple[Candidate, ...], tokens: int = 2000) -> None:
        self.candidates = candidates
        self.tokens = tokens
        self.last_billed_call: BilledCall | None = None

    def __call__(self, transcript: Any) -> tuple[Candidate, ...]:
        call = BilledCall(
            model="gemini-2.5-pro",
            tokens=self.tokens,
            cost_usd_estimate=estimate_cost_usd(self.tokens),
            stage="discovery",
            candidate_id=f"{transcript.media_id}-path-a",
        )
        self.last_billed_call = call
        return self.candidates


class MockJudgeWithCount:
    def __init__(self, verdict: JudgeVerdict, tokens: int = 4000) -> None:
        self.verdict = verdict
        self.tokens = tokens
        self.model_id = "gemini-2.5-pro"
        self.last_billed_call: BilledCall | None = None

    def judge_with_count(self, request: JudgeRequest) -> tuple[int, JudgeVerdict]:
        call = BilledCall(
            model=self.model_id,
            tokens=self.tokens,
            cost_usd_estimate=estimate_cost_usd(self.tokens),
            stage="editorial",
            candidate_id=request.candidate_id,
        )
        self.last_billed_call = call
        return self.tokens, self.verdict

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        return self.judge_with_count(request)[1]


def test_billed_call_validates_invariants() -> None:
    with pytest.raises(ValueError, match="model cannot be empty"):
        BilledCall(model="  ", tokens=100, cost_usd_estimate=0.0002, stage="editorial")
    with pytest.raises(ValueError, match="tokens must be non-negative"):
        BilledCall(model="gemini-2.5-pro", tokens=-1, cost_usd_estimate=0.0002, stage="editorial")
    with pytest.raises(ValueError, match="cost_usd_estimate cannot be negative"):
        BilledCall(model="gemini-2.5-pro", tokens=100, cost_usd_estimate=-0.1, stage="editorial")
    with pytest.raises(ValueError, match="stage cannot be empty"):
        BilledCall(model="gemini-2.5-pro", tokens=100, cost_usd_estimate=0.0002, stage="  ")

    call = BilledCall(
        model="gemini-2.5-pro",
        tokens=1000,
        cost_usd_estimate=0.002,
        stage="discovery",
        candidate_id="cand-1",
    )
    d = call.to_dict()
    assert d["model"] == "gemini-2.5-pro"
    assert d["tokens"] == 1000
    assert d["cost_usd_estimate"] == 0.002
    assert d["stage"] == "discovery"
    assert d["candidate_id"] == "cand-1"


def test_run_event_billed_state_roundtrips_through_jsonl(tmp_path: Path) -> None:
    ledger = tmp_path / "events.jsonl"
    sink = JsonlEventSink(ledger)
    log = RunEventLog("test-run", sink)

    log.started("discovery")
    billed_event = log.billed(
        stage="discovery",
        model="gemini-2.5-pro",
        tokens=2500,
        cost_usd_estimate=estimate_cost_usd(2500),
        candidate_id="cand-123",
    )
    log.finished("discovery")

    assert billed_event.state is RunState.BILLED
    assert billed_event.tokens == 2500
    assert billed_event.model == "gemini-2.5-pro"

    read_back = read_events(ledger)
    assert len(read_back) == 3
    event_read = read_back[1]
    assert event_read.state is RunState.BILLED
    assert event_read.model == "gemini-2.5-pro"
    assert event_read.tokens == 2500
    assert event_read.cost_usd_estimate == pytest.approx(estimate_cost_usd(2500))
    assert event_read.candidate_id == "cand-123"


@needs_ffmpeg
def test_every_billed_call_is_in_the_run_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    events: list[RunEvent] = []
    cands = (
        Candidate(
            "kurdish-speech-3cuts-0",
            "kurdish-speech-3cuts",
            100,
            4_100,
            DiscoveryPath.VERBAL,
            1,
            0.9,
        ),
    )
    discoverer = MockPathADiscoverer(cands, tokens=2000)
    verdict = a_verdict(100, 4_100)
    judge = MockJudgeWithCount(verdict, tokens=4000)

    run = run_pipeline(
        FIXTURE,
        work_dir=tmp_path / "work",
        transcript=a_transcript(),
        select_sentences=(0, 1),
        discover=discoverer,
        judge=judge,
        on_event=events.append,
    )

    # 1. Billed calls are on the run object
    assert len(run.billed_calls) == 2
    disc_call, judge_call = run.billed_calls

    assert disc_call.stage == "discovery"
    assert disc_call.model == "gemini-2.5-pro"
    assert disc_call.tokens == 2000
    assert disc_call.cost_usd_estimate == pytest.approx(estimate_cost_usd(2000))

    assert judge_call.stage == "editorial"
    assert judge_call.model == "gemini-2.5-pro"
    assert judge_call.tokens == 4000
    assert judge_call.cost_usd_estimate == pytest.approx(estimate_cost_usd(4000))

    # 2. Billed calls are in the serialized report dictionary
    report = run.to_dict()
    assert "billed_calls" in report
    assert len(report["billed_calls"]) == 2
    assert report["total_tokens_billed"] == 6000
    expected_cost = estimate_cost_usd(2000) + estimate_cost_usd(4000)
    assert report["total_cost_usd_estimate"] == pytest.approx(expected_cost, abs=1e-6)

    # 3. Every billed call emitted a RunState.BILLED event
    billed_events = [e for e in events if e.state is RunState.BILLED]
    assert len(billed_events) == 2
    assert billed_events[0].stage == "discovery"
    assert billed_events[0].tokens == 2000
    assert billed_events[1].stage == "editorial"
    assert billed_events[1].tokens == 4000

    # 4. Printed report displays the cost and token summary
    _print_report(run)
    captured = capsys.readouterr().out
    assert "billed  2 call(s) · 6,000 tokens" in captured
    assert "(estimate)" in captured
