"""Unit and integration tests for Judge Calibration (Task T4.3)."""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import hawedit.judge as judge_mod
from hawedit.boundary import BoundaryInputs, fuse_boundary
from hawedit.clip import (
    MIN_CULTURAL_LANDING,
    MIN_MEANING_FIDELITY,
    Clip,
    ClipTranscript,
    DiscoveryPath,
    Editorial,
    EditorialBelowThreshold,
    Output,
    Provenance,
    Qc,
    Sv6d,
)
from hawedit.discovery import Candidate, MergedCandidate
from hawedit.episode import EpisodePlanConfig, plan_episode, select_episode_plan
from hawedit.gemini import _PROMPT, JudgeUnusable
from hawedit.judge import (
    JUDGE_SHADOW,
    KURDISH_EDITORIAL_JUDGE,
    MAX_PAIRWISE_CANDIDATES,
    PAIRWISE_SCHEMA,
    PRO_TIER_TOKEN_CEILING,
    BilledCall,
    GeminiPairwiseJudge,
    JudgeRequest,
    JudgeVerdict,
    NotRoutable,
    PairwiseMatch,
    RequestTooLarge,
    assert_model_agreement_cannot_bypass_human_qc,
    compute_repeat_k_agreement,
    pairwise_rank_verdicts,
    tournament_rank_verdicts,
)
from hawedit.pipeline import StageSkipped, run_pipeline
from hawedit.repurposing import pairwise_preference
from hawedit.transcripts import AsrProvenance, RawTranscript, Word


def _make_verdict(
    candidate_id: str,
    hook_score: float,
    payoff_strength: float = 0.8,
    meaning_fidelity: float = 0.9,
    cultural_landing: float = 0.85,
    misleading_edit_risk: float = 0.05,
    ends_on_a_beat: bool = True,
    hook_type: str = "claim",
) -> JudgeVerdict:
    return JudgeVerdict(
        candidate_id=candidate_id,
        hook_score=hook_score,
        self_contained=True,
        payoff_at_ms=15_000,
        meaning_fidelity=meaning_fidelity,
        misleading_edit_risk=misleading_edit_risk,
        cultural_landing=cultural_landing,
        narrative_role="payoff",
        title_ckb="ناونیشانی نموونەیی",
        description_ckb="وەسفی نموونەیی بۆ بڵاوکردنەوە",
        hashtags_ckb=("#کوردستان", "#هەواڵ"),
        judge=KURDISH_EDITORIAL_JUDGE,
        clip_in_ms=0,
        clip_out_ms=25_000,
        hook_type=hook_type,
        payoff_strength=payoff_strength,
        ends_on_a_beat=ends_on_a_beat,
        reason_ckb="شیکاری و هەڵسەنگاندنی بابەتیانە.",
    )


def _make_clip(editorial: Editorial) -> Clip:
    boundary = fuse_boundary(
        BoundaryInputs(
            anchor_in_ms=0,
            anchor_out_ms=25_000,
            sentence_complete=True,
        )
    )
    words = (Word(w="کوردی", start_ms=0, end_ms=500, conf=0.9),)
    return Clip(
        clip_id="c-calib-1",
        media_id="m-calib-1",
        media_sha256="a" * 64,
        in_ms=boundary.final_in_ms,
        out_ms=boundary.final_out_ms,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=boundary,
        transcript=ClipTranscript(
            raw_ckb="کوردی",
            norm_ckb="کوردی",
            en_aux=None,
            words=words,
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        ),
        speaker="SPK_01",
        editorial=editorial,
        output=Output(
            title_ckb="ناونیشان",
            description_ckb="وەسف",
            crop_target="speaker_face",
            caption_style="word_highlight",
            durations=(30,),
        ),
        qc=Qc(
            auto_pass=True,
            flags=(),
            human_reviewed=True,
            reviewed_by="Hawa",
            reviewed_at="2026-09-02T19:00:00Z",
            reviewed_sha256="0" * 64,
        ),
        provenance=Provenance.current(),
    )


def _make_editorial(**overrides: object) -> Editorial:
    data: dict[str, object] = {
        "hook_score": 0.85,
        "self_contained": True,
        "meaning_fidelity": 0.90,
        "misleading_edit_risk": 0.05,
        "cultural_landing": 0.85,
        "narrative_role": "payoff",
        "judge": KURDISH_EDITORIAL_JUDGE,
        "sv6d": Sv6d(
            subject="speaker at desk [5.0s]",
            aesthetics="warm key light [6.0s]",
            camera="static medium [5.0s]",
            editing="single take [5.0s-20.0s]",
            narrative="payoff of the earlier claim [15.0s]",
            retention="raised voice holds attention [18.0s]",
        ),
    }
    data.update(overrides)
    return Editorial(**data)  # type: ignore[arg-type]


def test_prompt_template_contains_calibrated_sorani_rubric_anchors() -> None:
    """Prompt template contains explicit Sorani rubric anchors for 0.2, 0.5, and 0.8+."""
    assert "0.20:" in _PROMPT
    assert "0.50:" in _PROMPT
    assert "0.80+:" in _PROMPT
    assert "دەستپێکی ئاسایی" in _PROMPT
    assert "پرسیارێکی بوێرانە" in _PROMPT
    assert "Gated minimum floor: 0.70" in _PROMPT


def test_clip_assert_renderable_gates_meaning_fidelity() -> None:
    """Clips with meaning_fidelity below MIN_MEANING_FIDELITY (0.70) are rejected."""
    # Passing boundary case
    passing = _make_clip(editorial=_make_editorial(meaning_fidelity=MIN_MEANING_FIDELITY))
    passing.assert_renderable()

    # Failing case
    failing = _make_clip(editorial=_make_editorial(meaning_fidelity=0.69))
    with pytest.raises(
        EditorialBelowThreshold, match="meaning fidelity 0.69, below the 0.70 floor"
    ):
        failing.assert_renderable()


def test_clip_assert_renderable_gates_cultural_landing() -> None:
    """Clips with cultural_landing below MIN_CULTURAL_LANDING (0.70) are rejected."""
    # Passing boundary case
    passing = _make_clip(editorial=_make_editorial(cultural_landing=MIN_CULTURAL_LANDING))
    passing.assert_renderable()

    # Failing case
    failing = _make_clip(editorial=_make_editorial(cultural_landing=0.65))
    with pytest.raises(
        EditorialBelowThreshold, match="cultural landing 0.65, below the 0.70 floor"
    ):
        failing.assert_renderable()


def test_tournament_rank_verdicts_ranks_by_multidimensional_quality() -> None:
    """Pairwise ranking lets complete resolution beat raw hook bait without asserted weights."""
    # v1: strong hook (0.85) but weak payoff (0.20) and no clean beat
    v1 = _make_verdict(
        "v1",
        hook_score=0.85,
        payoff_strength=0.20,
        ends_on_a_beat=False,
        hook_type="claim",
    )
    # v2: slightly lower hook (0.80) but stellar payoff (0.95) and clean landing beat
    v2 = _make_verdict(
        "v2",
        hook_score=0.80,
        payoff_strength=0.95,
        ends_on_a_beat=True,
        hook_type="question",
    )

    class _PayoffComparator:
        def compare(
            self,
            verdict_a: JudgeVerdict,
            verdict_b: JudgeVerdict,
            *,
            text_a_ckb: str = "",
            text_b_ckb: str = "",
        ) -> PairwiseMatch:
            winner = (
                verdict_a.candidate_id
                if verdict_a.payoff_strength >= verdict_b.payoff_strength
                else verdict_b.candidate_id
            )
            return PairwiseMatch(
                candidate_a=verdict_a.candidate_id,
                candidate_b=verdict_b.candidate_id,
                winner=winner,
                reason_ckb="پەیوەندیی سەرەتا و کۆتایی تەواوترە.",
            )

    ranked = tournament_rank_verdicts([v1, v2], comparator=_PayoffComparator())
    assert len(ranked) == 2
    assert ranked[0][0].candidate_id == "v2"
    assert ranked[1][0].candidate_id == "v1"
    assert ranked[0][1] > ranked[1][1]


def test_compute_repeat_k_agreement_calculates_metric_concordance() -> None:
    """Repeat-K calculations compute mean, standard deviation, and span range across trials."""
    v1 = _make_verdict("v", hook_score=0.80, payoff_strength=0.85)
    v2 = _make_verdict("v", hook_score=0.84, payoff_strength=0.85)
    v3 = _make_verdict("v", hook_score=0.88, payoff_strength=0.85)

    agreement = compute_repeat_k_agreement([v1, v2, v3])
    assert agreement["k"] == 3.0
    assert agreement["hook_score_mean"] == pytest.approx(0.84, abs=1e-3)
    assert agreement["hook_score_range"] == pytest.approx(0.08, abs=1e-3)
    assert agreement["hook_score_std"] > 0.0
    # Constant metric has 0 range and 0 std
    assert agreement["payoff_strength_range"] == 0.0
    assert agreement["payoff_strength_std"] == 0.0


def test_single_and_episode_modes_share_eligibility_and_ranking() -> None:
    """WHEN single-clip and episode selection evaluate the same candidates,
    THE system SHALL apply the same eligibility and stable ranking policy and
    record uncertainty without equating model agreement with human accuracy (AC-15).
    """
    # 1. Candidate pool with eligible and ineligible items
    c_top = MergedCandidate(
        candidate_id="c_top",
        media_id="ep01",
        in_ms=0,
        out_ms=30_000,
        discovery_path=DiscoveryPath.VERBAL,
        sources=("c_top",),
    )
    v_top = _make_verdict(
        "c_top",
        hook_score=0.92,
        payoff_strength=0.90,
        meaning_fidelity=0.95,
        misleading_edit_risk=0.02,
        hook_type="question",
    )

    c_second = MergedCandidate(
        candidate_id="c_second",
        media_id="ep01",
        in_ms=60_000,
        out_ms=90_000,
        discovery_path=DiscoveryPath.VERBAL,
        sources=("c_second",),
    )
    v_second = _make_verdict(
        "c_second",
        hook_score=0.85,
        payoff_strength=0.80,
        meaning_fidelity=0.90,
        misleading_edit_risk=0.03,
        hook_type="claim",
    )

    # Ineligible candidate: very high hook score, but fails meaning fidelity floor
    c_ineligible = MergedCandidate(
        candidate_id="c_ineligible",
        media_id="ep01",
        in_ms=120_000,
        out_ms=150_000,
        discovery_path=DiscoveryPath.VERBAL,
        sources=("c_ineligible",),
    )
    v_ineligible = _make_verdict(
        "c_ineligible",
        hook_score=0.99,  # Highest hook
        payoff_strength=0.95,
        meaning_fidelity=0.50,  # Below 0.70 floor
        misleading_edit_risk=0.25,  # Above 0.10 ceiling
        hook_type="contrast",
    )

    pool = [
        (c_top, (0,), v_top),
        (c_second, (1,), v_second),
        (c_ineligible, (2,), v_ineligible),
    ]

    # 2. Single-clip ranking applies hard eligibility
    single_ranked = tournament_rank_verdicts([v_top, v_second, v_ineligible], require_eligible=True)
    assert len(single_ranked) == 2
    assert single_ranked[0][0].candidate_id == "c_top"
    assert single_ranked[1][0].candidate_id == "c_second"
    # c_ineligible is filtered out before ranking
    assert all(v[0].candidate_id != "c_ineligible" for v in single_ranked)

    # 3. Episode mode shares identical eligibility and stable ranking
    config = EpisodePlanConfig(max_clips=3, min_separation_ms=10_000)
    episode_selected = select_episode_plan(pool, config, require_eligible=True)

    # Episode mode returns only 2 clips; refuses to fill max_clips=3 with ineligible candidate
    assert len(episode_selected) == 2
    assert episode_selected[0][0].candidate_id == "c_top"
    assert episode_selected[1][0].candidate_id == "c_second"

    # Single-clip mode top pick and episode mode top pick are identical
    assert episode_selected[0][0].candidate_id == single_ranked[0][0].candidate_id

    # 4. Uncertainty recording without equating model agreement with human accuracy
    # Repeat evaluations across K=3 trials
    v_top_run2 = _make_verdict("c_top", hook_score=0.90, payoff_strength=0.88)
    v_top_run3 = _make_verdict("c_top", hook_score=0.94, payoff_strength=0.92)
    agreement = compute_repeat_k_agreement([v_top, v_top_run2, v_top_run3])

    assert agreement["k"] == 3.0
    assert agreement["hook_score_mean"] == pytest.approx(0.92, abs=1e-2)
    assert agreement["hook_score_std"] > 0.0
    assert agreement["hook_score_range"] == pytest.approx(0.04, abs=1e-3)

    # Even with 100% agreement across models/runs, automated agreement cannot bypass human QC
    v_identical = [v_top, v_top, v_top]
    identical_agreement = compute_repeat_k_agreement(v_identical)
    assert identical_agreement["hook_score_std"] == 0.0

    # No human review record -> cannot authorize delivery
    with pytest.raises(ValueError, match="Model agreement cannot equate to human accuracy"):
        assert_model_agreement_cannot_bypass_human_qc(v_identical, qc_record=None)

    # Human QC record with reject -> cannot authorize delivery
    from hawedit.clip import QcRecord

    reject_qc = QcRecord(
        reviewer="KurdishEditor",
        reviewed_at="2026-09-17T14:00:00Z",
        mp4_sha256="e" * 64,
        seconds_watched=45.0,
        verdict="reject",
        notes="Unverified claim",
    )
    with pytest.raises(ValueError, match="non-approved verdict"):
        assert_model_agreement_cannot_bypass_human_qc(v_identical, qc_record=reject_qc)

    # Approved QC record authorizes delivery
    approved_qc = QcRecord(
        reviewer="KurdishEditor",
        reviewed_at="2026-09-17T14:00:00Z",
        mp4_sha256="e" * 64,
        seconds_watched=45.0,
        verdict="approved",
        notes="All standards met",
    )
    assert_model_agreement_cannot_bypass_human_qc(v_identical, qc_record=approved_qc)


_CALIB_FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"
)


def _calib_transcript() -> RawTranscript:
    fixture_sha = hashlib.sha256(_CALIB_FIXTURE.read_bytes()).hexdigest()
    return RawTranscript(
        media_id="calib_fixture",
        text_ckb="ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=(
            Word(w="ڕۆژنامەوانی", start_ms=100, end_ms=800, conf=0.95),
            Word(w="کوردی.", start_ms=800, end_ms=1_700, conf=0.94),
            Word(w="لە", start_ms=2_000, end_ms=2_400, conf=0.93),
            Word(w="هەولێر.", start_ms=2_400, end_ms=4_100, conf=0.92),
        ),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=fixture_sha,
    )


class _TwoCandidateRecordingJudge:
    model_id = KURDISH_EDITORIAL_JUDGE

    def __init__(self, verdicts_by_id: dict[str, JudgeVerdict]) -> None:
        self._verdicts_by_id = verdicts_by_id
        self.calls: list[JudgeRequest] = []

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        self.calls.append(request)
        return self._verdicts_by_id[request.candidate_id]


def test_asserted_weights_retired_and_no_virality_score_emitted() -> None:
    """C5 AC1: 0.40/0.30/0.20/0.10 asserted formula is retired and zero virality score appears."""
    assert not hasattr(judge_mod, "tournament_score")
    source = inspect.getsource(judge_mod)
    assert "0.40 *" not in source
    assert "0.30 *" not in source
    assert "virality" not in source.lower()
    assert "virality" not in json.dumps(PAIRWISE_SCHEMA).lower()
    # Gemini REST API responseSchema (OpenAPI 3.0) rejects additionalProperties with HTTP 400.
    assert "additionalProperties" not in json.dumps(PAIRWISE_SCHEMA)


def test_pairwise_judge_schema_sorani_reason_and_refusals() -> None:
    """C5 AC2: GeminiPairwiseJudge asks keep-watching question, enforces Sorani & NotRoutable."""

    class _FakeJsonClient:
        def __init__(self, model_id: str, payload: str, *, tokens: int = 120) -> None:
            self.model_id = model_id
            self._payload = payload
            self._tokens = tokens
            self.seen_parts: list[list[dict[str, Any]]] = []
            self.seen_schemas: list[Mapping[str, Any]] = []

        def count_parts(self, parts: list[dict[str, Any]]) -> int:
            self.seen_parts.append(parts)
            return self._tokens

        def generate_json(self, parts: list[dict[str, Any]], schema: Mapping[str, Any]) -> str:
            self.seen_schemas.append(schema)
            return self._payload

    v_a = _make_verdict("cand_a", hook_score=0.80)
    v_b = _make_verdict("cand_b", hook_score=0.90)

    client = _FakeJsonClient(
        KURDISH_EDITORIAL_JUDGE,
        json.dumps({"winner": "A", "reason_ckb": "چیرۆکەکە تەواوە و گوێگر ڕادەگرێت."}),
    )
    pair_judge = GeminiPairwiseJudge(client)
    match = pair_judge.compare(
        v_a,
        v_b,
        text_a_ckb="دەقی كوردی یەکەم.",
        text_b_ckb="دەقی كوردی دووەم.",
    )
    assert match.candidate_a == "cand_a"
    assert match.candidate_b == "cand_b"
    assert match.winner == "cand_a"
    assert "ک" in match.reason_ckb
    assert match.billed_call == BilledCall(
        model=KURDISH_EDITORIAL_JUDGE,
        tokens=120,
        cost_usd_estimate=match.billed_call.cost_usd_estimate if match.billed_call else 0.0,
        stage="editorial",
        candidate_id="cand_a_vs_cand_b",
    )
    assert client.seen_schemas == [PAIRWISE_SCHEMA]
    prompt_text = client.seen_parts[0][0]["text"]
    assert "keep watching" in prompt_text.lower()
    assert "virality" not in prompt_text.lower()
    assert "دەقی کوردی یەکەم." in prompt_text
    assert "دەقی کوردی دووەم." in prompt_text

    # Shadow model is evaluated, not routed -> NotRoutable
    shadow_judge = GeminiPairwiseJudge(
        _FakeJsonClient(JUDGE_SHADOW, json.dumps({"winner": "A", "reason_ckb": "کوردی"}))
    )
    with pytest.raises(NotRoutable):
        shadow_judge.compare(v_a, v_b, text_a_ckb="یەک", text_b_ckb="دوو")

    # Token count at or above 200K ceiling -> RequestTooLarge
    huge_judge = GeminiPairwiseJudge(
        _FakeJsonClient(
            KURDISH_EDITORIAL_JUDGE,
            json.dumps({"winner": "A", "reason_ckb": "کوردی"}),
            tokens=PRO_TIER_TOKEN_CEILING,
        )
    )
    with pytest.raises(RequestTooLarge):
        huge_judge.compare(v_a, v_b, text_a_ckb="یەک", text_b_ckb="دوو")

    # Malformed / wrong winner / English-only reason -> JudgeUnusable (ValueError)
    for bad_payload in (
        "not json",
        json.dumps({"winner": "C", "reason_ckb": "کوردی"}),
        json.dumps({"winner": "B", "reason_ckb": "Better English hook"}),
    ):
        bad_judge = GeminiPairwiseJudge(_FakeJsonClient(KURDISH_EDITORIAL_JUDGE, bad_payload))
        with pytest.raises(JudgeUnusable):
            bad_judge.compare(v_a, v_b, text_a_ckb="یەک", text_b_ckb="دوو")


def test_pairwise_ranking_filters_ineligible_before_bouts() -> None:
    """C5 AC3: Ineligible verdicts are excluded BEFORE scheduling any pairwise bout."""
    eligible_1 = _make_verdict("e1", hook_score=0.76, meaning_fidelity=0.88)
    eligible_2 = _make_verdict("e2", hook_score=0.80, meaning_fidelity=0.92)
    low_fidelity = _make_verdict("bad_fid", hook_score=0.99, meaning_fidelity=0.69)
    high_risk = _make_verdict("bad_risk", hook_score=0.99, misleading_edit_risk=0.11)
    not_self_contained = replace(
        _make_verdict("bad_frag", hook_score=0.99),
        self_contained=False,
    )

    seen_pairs: list[tuple[str, str]] = []

    class _RecordingComparator:
        def compare(
            self,
            verdict_a: JudgeVerdict,
            verdict_b: JudgeVerdict,
            *,
            text_a_ckb: str = "",
            text_b_ckb: str = "",
        ) -> PairwiseMatch:
            seen_pairs.append((verdict_a.candidate_id, verdict_b.candidate_id))
            winner = (
                verdict_a.candidate_id
                if verdict_a.meaning_fidelity >= verdict_b.meaning_fidelity
                else verdict_b.candidate_id
            )
            return PairwiseMatch(
                candidate_a=verdict_a.candidate_id,
                candidate_b=verdict_b.candidate_id,
                winner=winner,
                reason_ckb="دڵنیایی مانا لەپێشترە.",
            )

    ranked = pairwise_rank_verdicts(
        [eligible_1, low_fidelity, high_risk, not_self_contained, eligible_2],
        comparator=_RecordingComparator(),
    )
    assert [v.candidate_id for v, _ in ranked] == ["e2", "e1"]
    assert seen_pairs
    assert all(cid in {"e1", "e2"} for pair in seen_pairs for cid in pair), (
        f"ineligible candidate entered bout: {seen_pairs}"
    )


def test_swiss_tournament_ranks_top_candidates_via_pairwise_win_rate() -> None:
    """C5 AC4: Bounded <=12 Swiss tournament swaps A/B positions & applies Buchholz tiebreak."""
    # Construct 15 eligible candidates so cap at MAX_PAIRWISE_CANDIDATES (12) is verified.
    verdicts = [_make_verdict(f"c{idx:02d}", hook_score=0.95 - idx * 0.01) for idx in range(15)]
    matches: list[PairwiseMatch] = []

    class _DeterministicComparator:
        def compare(
            self,
            verdict_a: JudgeVerdict,
            verdict_b: JudgeVerdict,
            *,
            text_a_ckb: str = "",
            text_b_ckb: str = "",
        ) -> PairwiseMatch:
            # Inverted order vs raw hook_score: larger numeric index wins cleanly.
            num_a = int(verdict_a.candidate_id[1:])
            num_b = int(verdict_b.candidate_id[1:])
            return PairwiseMatch(
                candidate_a=verdict_a.candidate_id,
                candidate_b=verdict_b.candidate_id,
                winner=verdict_a.candidate_id if num_a > num_b else verdict_b.candidate_id,
                reason_ckb="ئەنجامی تەواوتر پێشکەش دەکات.",
            )

    ranked = pairwise_rank_verdicts(
        verdicts,
        comparator=_DeterministicComparator(),
        rounds=3,
        max_candidates=MAX_PAIRWISE_CANDIDATES,
        matches_out=matches,
    )
    assert len(ranked) == MAX_PAIRWISE_CANDIDATES
    # Only top 12 by pre-cap order (c00..c11) enter; true strongest (c11) finishes undefeated.
    assert {v.candidate_id for v, _ in ranked} == {f"c{idx:02d}" for idx in range(12)}
    assert ranked[0][1] == 1.0

    # Verify aggregation matches repurposing.pairwise_preference exactly
    raw_rates = pairwise_preference([(m.candidate_a, m.candidate_b, m.winner) for m in matches])
    assert raw_rates["c11"] == 1.0
    for verd, reported_score in ranked:
        assert reported_score == pytest.approx(raw_rates[verd.candidate_id], abs=1e-4)

    # On 8 candidates across 3 rounds (2^3 = 8), inverted Swiss leaves c07 undefeated.
    ranked_eight = pairwise_rank_verdicts(
        verdicts[:8], comparator=_DeterministicComparator(), rounds=3
    )
    assert ranked_eight[0][0].candidate_id == "c07"
    assert ranked_eight[0][1] == 1.0

    # Verify A/B slot alternation across the tournament (same candidate appears in both slots)
    a_appearances = {m.candidate_a for m in matches}
    b_appearances = {m.candidate_b for m in matches}
    assert len(a_appearances & b_appearances) >= 6

    # Verify round bounds guard
    with pytest.raises(ValueError, match="rounds"):
        pairwise_rank_verdicts(verdicts[:4], comparator=_DeterministicComparator(), rounds=1)
    with pytest.raises(ValueError, match="max_candidates"):
        pairwise_rank_verdicts(verdicts, comparator=_DeterministicComparator(), max_candidates=13)

    # Explicit Buchholz tiebreak check on 6 candidates:
    v_six = [_make_verdict(f"q{i}", hook_score=0.80) for i in range(6)]
    six_table: dict[frozenset[str], str | None] = {
        frozenset({"q0", "q1"}): "q0",  # R1: q0>q1, q2>q3, q4>q5 -> winners q0,q2,q4
        frozenset({"q2", "q3"}): "q2",
        frozenset({"q4", "q5"}): "q4",
        frozenset({"q0", "q2"}): "q0",  # R2: q0>q2 (q0=1.0, q2=0.5)
        frozenset({"q4", "q1"}): "q1",  # q1>q4 (q4=0.5, q1=0.5)
        frozenset({"q3", "q5"}): "q3",  # q3>q5 (q3=0.5, q5=0.0)
    }
    # Check ALL FOUR 0.5-win-rate players after R2:
    # q2 played q3 (0.5) + q0 (1.0) => Buchholz = 1.5!
    # q1 played q0 (1.0) + q4 (0.5) => Buchholz = 1.5!
    # q4 played q5 (0.0) + q1 (0.5) => Buchholz = 0.5!
    # q3 played q2 (0.5) + q5 (0.0) => Buchholz = 0.5!
    # q2 and q1 STRICTLY beat q4 and q3 by Buchholz even though all four have win_rate = 0.5!

    class _TableComparator:
        def compare(
            self,
            verdict_a: JudgeVerdict,
            verdict_b: JudgeVerdict,
            *,
            text_a_ckb: str = "",
            text_b_ckb: str = "",
        ) -> PairwiseMatch:
            winner = six_table[frozenset({verdict_a.candidate_id, verdict_b.candidate_id})]
            return PairwiseMatch(
                candidate_a=verdict_a.candidate_id,
                candidate_b=verdict_b.candidate_id,
                winner=winner,
                reason_ckb="ئەم بەراوردە تەواوترە.",
            )

    buchholz_ranked = pairwise_rank_verdicts(v_six, comparator=_TableComparator(), rounds=2)
    ordered_ids = [v.candidate_id for v, _ in buchholz_ranked]
    assert ordered_ids[0] == "q0"
    assert ordered_ids[-1] == "q5"
    assert set(ordered_ids[1:3]) == {"q1", "q2"}
    assert set(ordered_ids[3:5]) == {"q3", "q4"}


def test_pairwise_ranker_skips_llm_for_single_verdict_and_fails_loudly_on_error(
    tmp_path: Path,
) -> None:
    """C5 AC5: <=1 verdict issues zero bouts; comparator failure stops Stage 4 visibly."""
    calls = 0

    class _CountingFailComparator:
        def compare(
            self,
            verdict_a: JudgeVerdict,
            verdict_b: JudgeVerdict,
            *,
            text_a_ckb: str = "",
            text_b_ckb: str = "",
        ) -> PairwiseMatch:
            nonlocal calls
            calls += 1
            raise JudgeUnusable("pairwise judge returned invalid Sorani response")

    failing = _CountingFailComparator()
    assert pairwise_rank_verdicts([], comparator=failing) == ()
    single = pairwise_rank_verdicts([_make_verdict("only", hook_score=0.82)], comparator=failing)
    assert len(single) == 1 and single[0][0].candidate_id == "only"
    assert calls == 0

    # Pipeline with 2 shippable verdicts + failing comparator -> Stage 4 failure, no fallback
    v1 = replace(
        _make_verdict("v1", hook_score=0.90),
        clip_in_ms=100,
        clip_out_ms=1_700,
        payoff_at_ms=1_200,
    )
    v2 = replace(
        _make_verdict("v2", hook_score=0.80),
        clip_in_ms=2_000,
        clip_out_ms=4_100,
        payoff_at_ms=3_200,
    )
    judge = _TwoCandidateRecordingJudge({"v1": v1, "v2": v2})

    run = run_pipeline(
        _CALIB_FIXTURE,
        tmp_path / "work",
        media_id="calib_fixture",
        transcript=_calib_transcript(),
        discover=lambda _n: [
            Candidate("v1", "calib_fixture", 100, 1_700, DiscoveryPath.VERBAL, rank=1, score=0.9),
            Candidate("v2", "calib_fixture", 2_000, 4_100, DiscoveryPath.VERBAL, rank=2, score=0.8),
        ],
        judge=judge,
        auto_select=True,
        judge_top_n=2,
        min_clip_ms=1_500,
        pairwise_comparator=failing,
    )
    assert calls >= 1
    assert isinstance(run.editorial, StageSkipped)
    assert run.clip is None


def test_single_and_episode_modes_share_pairwise_ranking_and_eligibility(
    tmp_path: Path,
) -> None:
    """C5 AC6: Single-clip Stage 4 and episode planning agree on pairwise ranking & eligibility."""
    # Even though v1 has higher hook_score (0.93 > 0.78), pairwise judge prefers v2.
    v1 = replace(
        _make_verdict("v1", hook_score=0.93, payoff_strength=0.40),
        clip_in_ms=100,
        clip_out_ms=1_700,
        payoff_at_ms=1_200,
    )
    v2 = replace(
        _make_verdict("v2", hook_score=0.78, payoff_strength=0.96),
        clip_in_ms=2_000,
        clip_out_ms=4_100,
        payoff_at_ms=3_200,
    )

    class _PrefComparator:
        def compare(
            self,
            verdict_a: JudgeVerdict,
            verdict_b: JudgeVerdict,
            *,
            text_a_ckb: str = "",
            text_b_ckb: str = "",
        ) -> PairwiseMatch:
            winner: str | None = verdict_a.candidate_id
            if verdict_b.payoff_strength > verdict_a.payoff_strength:
                winner = verdict_b.candidate_id
            elif verdict_a.payoff_strength == verdict_b.payoff_strength:
                winner = None
            return PairwiseMatch(
                candidate_a=verdict_a.candidate_id,
                candidate_b=verdict_b.candidate_id,
                winner=winner,
                reason_ckb="ئەم پارچەیە واتای تەواوتر و سەرەنجڕاکێشتری هەیە.",
            )

    comp = _PrefComparator()
    transcript = _calib_transcript()
    candidates = [
        Candidate("v1", "calib_fixture", 100, 1_700, DiscoveryPath.VERBAL, rank=1, score=0.9),
        Candidate("v2", "calib_fixture", 2_000, 4_100, DiscoveryPath.VERBAL, rank=2, score=0.8),
    ]

    run_single = run_pipeline(
        _CALIB_FIXTURE,
        tmp_path / "single",
        media_id="calib_fixture",
        transcript=transcript,
        discover=lambda _n: candidates,
        judge=_TwoCandidateRecordingJudge({"v1": v1, "v2": v2}),
        auto_select=True,
        judge_top_n=2,
        min_clip_ms=1_500,
        pairwise_comparator=comp,
    )
    run_episode = run_pipeline(
        _CALIB_FIXTURE,
        tmp_path / "episode",
        media_id="calib_fixture",
        transcript=transcript,
        discover=lambda _n: candidates,
        judge=_TwoCandidateRecordingJudge({"v1": v1, "v2": v2}),
        auto_select=True,
        judge_top_n=2,
        min_clip_ms=1_500,
        max_clips=2,
        min_separation_ms=1_000,
        pairwise_comparator=comp,
    )
    assert run_single.clip is not None
    assert run_single.clip.in_ms >= 1_800
    assert run_episode.episode_manifest is not None
    assert len(run_episode.episode_manifest.clips) == 1
    assert run_episode.episode_manifest.clips[0].in_ms == run_single.clip.in_ms

    # Also verify EpisodePlanConfig separation & eligibility rejection in plan_episode directly
    c_win = MergedCandidate("win", "ep", 0, 25_000, DiscoveryPath.VERBAL, ("win",))
    v_win = replace(
        _make_verdict("win", hook_score=0.77, payoff_strength=0.97),
        clip_in_ms=0,
        clip_out_ms=25_000,
    )
    c_too_close = MergedCandidate("close", "ep", 26_000, 50_000, DiscoveryPath.VERBAL, ("close",))
    v_close = replace(
        _make_verdict("close", hook_score=0.90, payoff_strength=0.90),
        clip_in_ms=26_000,
        clip_out_ms=50_000,
        payoff_at_ms=35_000,
    )
    c_far = MergedCandidate("far", "ep", 60_000, 85_000, DiscoveryPath.VERBAL, ("far",))
    v_far = replace(
        _make_verdict("far", hook_score=0.91, payoff_strength=0.60),
        clip_in_ms=60_000,
        clip_out_ms=85_000,
        payoff_at_ms=72_000,
    )
    c_bad = MergedCandidate("bad", "ep", 100_000, 125_000, DiscoveryPath.VERBAL, ("bad",))
    v_bad = replace(
        _make_verdict("bad", hook_score=0.99, payoff_strength=0.99, meaning_fidelity=0.40),
        clip_in_ms=100_000,
        clip_out_ms=125_000,
        payoff_at_ms=112_000,
    )
    selected_ep, _records = plan_episode(
        [
            (c_far, (0,), v_far),
            (c_too_close, (1,), v_close),
            (c_bad, (2,), v_bad),
            (c_win, (3,), v_win),
        ],
        EpisodePlanConfig(max_clips=2, min_separation_ms=10_000),
        comparator=comp,
    )
    assert [c.candidate_id for c, _, _ in selected_ep] == ["win", "far"]


def test_episode_mode_with_zero_judged_candidates_does_not_crash_on_unbound_comparator(
    tmp_path: Path,
) -> None:
    """Episode delivery with 0 candidates must return cleanly instead of UnboundLocalError."""
    fixture = Path(__file__).parent / "fixtures" / "kurdish-speech-3cuts.mp4"
    run = run_pipeline(
        source=fixture,
        work_dir=tmp_path / "work",
        media_id="calib_fixture",
        transcript=_calib_transcript(),
        discover=lambda _norm: (),
        auto_select=True,
        max_clips=3,
    )
    assert run.episode_manifest is not None
    assert run.episode_manifest.is_no_clip_outcome is True
    assert run.episode_manifest.clips == ()


def test_pairwise_judge_unwraps_gemini_envelope_skipping_thought_parts() -> None:
    """Live GeminiJudge.generate_json returns a generateContent envelope with thought parts."""

    class _EnvelopeClient:
        model_id = KURDISH_EDITORIAL_JUDGE

        def count_parts(self, parts: list[dict[str, Any]]) -> int:
            return 80

        def generate_json(self, parts: list[dict[str, Any]], schema: Mapping[str, Any]) -> str:
            return json.dumps(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"thought": True, "text": "internal reasoning"},
                                    {
                                        "text": json.dumps(
                                            {
                                                "winner": "B",
                                                "reason_ckb": "کۆتایی دووەم بەهێزترە و تەواوترە.",
                                            }
                                        )
                                    },
                                ]
                            }
                        }
                    ],
                    "modelVersion": KURDISH_EDITORIAL_JUDGE,
                }
            )

    match = GeminiPairwiseJudge(_EnvelopeClient()).compare(
        _make_verdict("cand_a", hook_score=0.80),
        _make_verdict("cand_b", hook_score=0.85),
        text_a_ckb="دەقی یەکەم.",
        text_b_ckb="دەقی دووەم.",
    )
    assert match.winner == "cand_b"
    assert "دووەم" in match.reason_ckb


def test_episode_delivery_rejects_below_hook_floor_before_overlap_selection(
    tmp_path: Path,
) -> None:
    """An unshippable hook<0.75 candidate must not steal overlap slots or cause partial failure."""
    weak_overlap = replace(
        _make_verdict("weak", hook_score=0.68, payoff_strength=0.95),
        clip_in_ms=100,
        clip_out_ms=1_700,
        payoff_at_ms=1_200,
    )
    strong_overlap = replace(
        _make_verdict("strong", hook_score=0.78, payoff_strength=0.80),
        clip_in_ms=100,
        clip_out_ms=1_700,
        payoff_at_ms=1_200,
    )
    candidates = [
        Candidate("weak", "calib_fixture", 100, 1_700, DiscoveryPath.VERBAL, rank=1, score=0.95),
        Candidate("strong", "calib_fixture", 100, 1_700, DiscoveryPath.VERBAL, rank=2, score=0.85),
    ]
    bouts: list[tuple[str, str]] = []

    class _CountingComparator:
        def compare(
            self,
            verdict_a: JudgeVerdict,
            verdict_b: JudgeVerdict,
            *,
            text_a_ckb: str = "",
            text_b_ckb: str = "",
        ) -> PairwiseMatch:
            bouts.append((verdict_a.candidate_id, verdict_b.candidate_id))
            return PairwiseMatch(
                candidate_a=verdict_a.candidate_id,
                candidate_b=verdict_b.candidate_id,
                winner=verdict_a.candidate_id,
                reason_ckb="هەڵبژاردنی یەکەم.",
            )

    run = run_pipeline(
        _CALIB_FIXTURE,
        tmp_path / "episode_shippable",
        media_id="calib_fixture",
        transcript=_calib_transcript(),
        discover=lambda _n: candidates,
        judge=_TwoCandidateRecordingJudge({"weak": weak_overlap, "strong": strong_overlap}),
        auto_select=True,
        judge_top_n=2,
        min_clip_ms=1_500,
        max_clips=2,
        min_separation_ms=1_000,
        pairwise_comparator=_CountingComparator(),
    )
    assert run.episode_manifest is not None
    assert run.episode_manifest.has_partial_failure is False
    assert len(run.episode_manifest.clips) == 1
    assert [r.candidate_id for r in run.episode_manifest.pending_review_items] == ["strong"]
    assert bouts == []
    rejected = {r.candidate_id: r for r in run.episode_manifest.rejected_items}
    assert "weak" in rejected
    assert rejected["weak"].rejection_reason is not None
    assert "hook=0.68" in rejected["weak"].rejection_reason
