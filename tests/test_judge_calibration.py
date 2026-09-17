"""Unit and integration tests for Judge Calibration (Task T4.3)."""

from __future__ import annotations

import pytest

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
from hawedit.discovery import MergedCandidate
from hawedit.episode import EpisodePlanConfig, select_episode_plan
from hawedit.gemini import _PROMPT
from hawedit.judge import (
    JudgeVerdict,
    assert_model_agreement_cannot_bypass_human_qc,
    compute_repeat_k_agreement,
    tournament_rank_verdicts,
    tournament_score,
)
from hawedit.transcripts import AsrProvenance, Word


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
        judge="gemini-2.5-pro",
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
        "judge": "gemini-2.5-pro",
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
    """Multi-dimensional scoring rewards complete resolution over raw hook noise."""
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

    ranked = tournament_rank_verdicts([v1, v2])
    assert len(ranked) == 2
    # v2 should rank higher than v1 due to complete narrative satisfaction and beat landing
    assert ranked[0][0].candidate_id == "v2"
    assert ranked[1][0].candidate_id == "v1"
    assert tournament_score(v2) > tournament_score(v1)


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
