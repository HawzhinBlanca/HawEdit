"""Tests for Candidate Screener Funnel (D-275, specs/fast-candidate-screener)."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import pytest

from hawedit.clip import DiscoveryPath
from hawedit.credentials import CredentialError
from hawedit.discovery import Candidate, MergedCandidate
from hawedit.judge import JudgeRequest, JudgeVerdict
from hawedit.pipeline import run_pipeline
from hawedit.screener import (
    GeminiFlashScreener,
    JevScreener,
    ScreenedCandidate,
    calculate_screener_score,
    get_screener,
)
from hawedit.transcripts import AsrProvenance, RawTranscript, Word


def _make_candidate(cid: str) -> MergedCandidate:
    return MergedCandidate(
        candidate_id=cid,
        media_id="ep29",
        in_ms=1000,
        out_ms=35000,
        discovery_path=DiscoveryPath.VERBAL,
        sources=(cid,),
    )


def test_calculate_screener_score() -> None:
    # If not self-contained, score is zero
    assert (
        calculate_screener_score(
            hook_score=0.9, payoff_score=0.9, misleading_risk=0.1, is_self_contained=False
        )
        == 0.0
    )

    # High hook, high payoff, low risk
    score = calculate_screener_score(
        hook_score=0.9, payoff_score=0.8, misleading_risk=0.1, is_self_contained=True
    )
    # 0.50*0.9 + 0.35*0.8 + 0.15*(1.0-0.1) = 0.45 + 0.28 + 0.135 = 0.865
    assert score == 0.865


def test_screened_candidate_validation() -> None:
    with pytest.raises(ValueError, match="hook_score must be in"):
        ScreenedCandidate(
            candidate_id="c1",
            hook_score=1.5,
            payoff_score=0.5,
            is_self_contained=True,
            misleading_risk=0.1,
            composite_score=0.5,
            screener="test",
        )


def test_gemini_flash_screener_success() -> None:
    c1 = _make_candidate("c1")
    c2 = _make_candidate("c2")

    mock_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "candidates": [
                                        {
                                            "candidate_id": "c1",
                                            "hook_score": 0.4,
                                            "payoff_score": 0.5,
                                            "is_self_contained": True,
                                            "misleading_risk": 0.2,
                                        },
                                        {
                                            "candidate_id": "c2",
                                            "hook_score": 0.9,
                                            "payoff_score": 0.8,
                                            "is_self_contained": True,
                                            "misleading_risk": 0.1,
                                        },
                                    ]
                                }
                            )
                        }
                    ]
                }
            }
        ]
    }

    def mock_transport(req: urllib.request.Request) -> bytes:
        return json.dumps(mock_response).encode("utf-8")

    screener = GeminiFlashScreener(api_key="mock_key", transport=mock_transport)
    results = screener.screen([(c1, "text 1"), (c2, "text 2")], top_k=2)

    assert len(results) == 2
    # c2 must rank higher than c1
    assert results[0].candidate_id == "c2"
    assert results[0].hook_score == 0.9
    assert results[1].candidate_id == "c1"


def test_gemini_flash_screener_empty() -> None:
    screener = GeminiFlashScreener(api_key="mock_key", transport=lambda r: b"")
    assert screener.screen(()) == ()


def test_gemini_flash_screener_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("hawedit.credentials.read_credential", lambda name: None)
    with pytest.raises(CredentialError, match="GEMINI_API_KEY is required"):
        GeminiFlashScreener(api_key=None)


def test_jev_screener_success() -> None:
    c1 = _make_candidate("c1")

    mock_jev_response = {
        "questions": {
            "is_self_contained": {"answer": True},
            "hook_score": {"answer": 88.0},
            "payoff_score": {"answer": 75.0},
            "misleading_risk": {"probability": 0.05},
        }
    }

    def mock_transport(req: urllib.request.Request) -> bytes:
        assert req.headers.get("Authorization") == "Bearer test_jev_key"
        return json.dumps(mock_jev_response).encode("utf-8")

    screener = JevScreener(api_key="test_jev_key", transport=mock_transport)
    results = screener.screen([(c1, "Kurdish transcript text")], top_k=1)

    assert len(results) == 1
    assert results[0].candidate_id == "c1"
    assert results[0].hook_score == 0.88
    assert results[0].payoff_score == 0.75
    assert results[0].is_self_contained is True
    assert results[0].misleading_risk == 0.05
    assert results[0].composite_score > 0.7


def test_jev_screener_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr("hawedit.credentials.read_credential", lambda name: None)
    with pytest.raises(CredentialError, match="TYPESAFE_API_KEY is required"):
        JevScreener(api_key=None)


def test_get_screener_factory() -> None:
    assert get_screener(None) is None
    assert get_screener("none") is None
    assert get_screener("off") is None

    gem = get_screener("gemini-flash", gemini_key="mock_key")
    assert isinstance(gem, GeminiFlashScreener)

    jev = get_screener("jev", typesafe_key="mock_key")
    assert isinstance(jev, JevScreener)

    with pytest.raises(ValueError, match="Unknown screener name"):
        get_screener("unknown-ai-model")


FIXTURE: Final = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"
)
FIXTURE_SHA256: Final = "ed038e743a6b1ee167290741ceda926ac1077ff192e4910528017e3183655a15"
_WORDS: Final = (
    Word(w="ڕۆژنامەوانی", start_ms=100, end_ms=800, conf=0.95),
    Word(w="کوردی.", start_ms=800, end_ms=1_700, conf=0.94),
    Word(w="لە", start_ms=2_000, end_ms=2_400, conf=0.93),
    Word(w="هەولێر.", start_ms=2_400, end_ms=4_100, conf=0.92),
)


def _a_transcript(media_id: str = "fixture") -> RawTranscript:
    return RawTranscript(
        media_id=media_id,
        text_ckb="ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=_WORDS,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=FIXTURE_SHA256,
    )


class MockEditorialJudge:
    model_id = "gemini-2.5-pro"
    requires_keyframes = False

    def __init__(self) -> None:
        self.judged_ids: list[str] = []

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        self.judged_ids.append(request.candidate_id)
        return JudgeVerdict(
            hook_score=0.95,
            misleading_edit_risk=0.05,
            self_contained=True,
            payoff_at_ms=(request.clip_in_ms + request.clip_out_ms) // 2,
            meaning_fidelity=0.98,
            cultural_landing=0.95,
            narrative_role="payoff",
            title_ckb="سەردێڕی تاقیکاری",
            description_ckb="وەسفی تاقیکاری",
            hashtags_ckb=("#کوردستان",),
            reason_ckb="هۆکاری پەسەندکردن",
            judge=self.model_id,
            clip_in_ms=request.clip_in_ms,
            clip_out_ms=request.clip_out_ms,
            candidate_id=request.candidate_id,
        )


class MockScreener:
    name = "mock-screener"

    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores
        self.screened_pairs: list[tuple[MergedCandidate, str]] = []

    def screen(
        self,
        candidates: Sequence[tuple[MergedCandidate, str]],
        *,
        top_k: int = 5,
    ) -> tuple[ScreenedCandidate, ...]:
        self.screened_pairs.extend(candidates)
        results = []
        for cand, _text in candidates:
            score = self.scores.get(cand.candidate_id, 0.5)
            results.append(
                ScreenedCandidate(
                    candidate_id=cand.candidate_id,
                    hook_score=score,
                    payoff_score=score,
                    is_self_contained=True,
                    misleading_risk=0.05,
                    composite_score=score,
                    screener=self.name,
                )
            )
        results.sort(key=lambda s: s.composite_score, reverse=True)
        return tuple(results[:top_k])


def test_pipeline_candidate_screening_funnel(tmp_path: Path) -> None:
    """Screening prunes/reorders candidates, passing the top survivor to the Judge (AC-1, AC-5)."""
    judge = MockEditorialJudge()
    screener = MockScreener({"cand_a": 0.20, "cand_b": 0.95})

    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="fixture",
        transcript=_a_transcript("fixture"),
        discover=lambda _n: [
            Candidate("cand_a", "fixture", 100, 1_700, DiscoveryPath.VERBAL, 1, 0.99),
            Candidate("cand_b", "fixture", 2_000, 4_100, DiscoveryPath.VERBAL, 2, 0.80),
        ],
        judge=judge,
        screener=screener,
        auto_select=True,
        judge_top_n=1,
        min_clip_ms=1_000,
    )

    assert run.clip is not None
    assert len(screener.screened_pairs) == 2
    assert judge.judged_ids == ["cand_b"]


def test_pipeline_screener_none_preserves_discovery_ranking(tmp_path: Path) -> None:
    """When screener is None/none, discovery priority governs Stage 4 (AC-6)."""
    judge = MockEditorialJudge()
    run = run_pipeline(
        FIXTURE,
        tmp_path / "work",
        media_id="fixture",
        transcript=_a_transcript("fixture"),
        discover=lambda _n: [
            Candidate("cand_a", "fixture", 100, 1_700, DiscoveryPath.VERBAL, 1, 0.99),
            Candidate("cand_b", "fixture", 2_000, 4_100, DiscoveryPath.VERBAL, 2, 0.80),
        ],
        judge=judge,
        screener=None,
        auto_select=True,
        judge_top_n=1,
        min_clip_ms=1_000,
    )

    assert run.clip is not None
    assert judge.judged_ids == ["cand_a"]


def test_pipeline_screener_jev_missing_key_fail_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Selecting Jev without TYPESAFE_API_KEY triggers fail-stop CredentialError (AC-4)."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr("hawedit.credentials.read_credential", lambda name: None)

    with pytest.raises(CredentialError, match="TYPESAFE_API_KEY is required"):
        run_pipeline(
            FIXTURE,
            tmp_path / "work",
            media_id="fixture",
            transcript=_a_transcript("fixture"),
            discover=lambda _n: [
                Candidate("cand_a", "fixture", 100, 1_700, DiscoveryPath.VERBAL, 1, 0.99),
            ],
            judge=MockEditorialJudge(),
            screener="jev",
            auto_select=True,
            min_clip_ms=1_000,
        )
