"""Tests for visual scorecard and holdout evaluation (V15).

Verifies step V15 (VE-15):
- requires unseen current evidence with strict provenance,
- enforces complete accounting of all proposed clips and refusals,
- clusters by episode to avoid pseudo-replication,
- detects and excludes leaked/contaminated holdouts,
- strictly refuses unsupported leadership or 10/10 claims.
"""

from __future__ import annotations

import pytest

from hawedit.visual_scorecard import (
    CompetitorComparison,
    DatasetSplit,
    EvaluationProposalRecord,
    InsufficientClustersError,
    LeakedHoldoutError,
    ProvenanceRecord,
    StaleEvidenceError,
    UnaccountedClipsError,
    UnsupportedLeadershipClaimError,
    VisualScorecardConfig,
    assert_no_holdout_leakage,
    compute_visual_scorecard,
)


def test_visual_scorecard_requires_unseen_current_evidence_and_full_accounting() -> None:
    # 1. Contamination / Leakage Protection
    dev_split = DatasetSplit(
        name="dev_set",
        episode_ids=frozenset({"ep_dev_01", "ep_dev_02"}),
        speaker_ids=frozenset({"spk_01", "spk_02"}),
        media_hashes=frozenset({"hash_a", "hash_b"}),
    )
    leaked_holdout = DatasetSplit(
        name="holdout_set_contaminated",
        episode_ids=frozenset({"ep_dev_02", "ep_hold_03"}),  # ep_dev_02 leaked!
        speaker_ids=frozenset({"spk_03", "spk_04"}),
        media_hashes=frozenset({"hash_c", "hash_d"}),
    )
    with pytest.raises(LeakedHoldoutError, match="episodes overlap"):
        assert_no_holdout_leakage(dev_split, leaked_holdout)

    speaker_leaked_holdout = DatasetSplit(
        name="holdout_set_speaker_leak",
        episode_ids=frozenset({"ep_hold_04", "ep_hold_05"}),
        speaker_ids=frozenset({"spk_02", "spk_05"}),  # spk_02 leaked!
    )
    with pytest.raises(LeakedHoldoutError, match="speakers overlap"):
        assert_no_holdout_leakage(dev_split, speaker_leaked_holdout)

    clean_holdout = DatasetSplit(
        name="clean_unseen_holdout",
        episode_ids=frozenset({"ep_hold_01", "ep_hold_02", "ep_hold_03"}),
        speaker_ids=frozenset({"spk_10", "spk_11"}),
        media_hashes=frozenset({"hash_10", "hash_11"}),
    )
    # Clean holdout passes without error
    assert_no_holdout_leakage(dev_split, clean_holdout)

    # 2. Provenance & Current Evidence
    with pytest.raises(StaleEvidenceError, match="commit_sha"):
        ProvenanceRecord(
            commit_sha="bad",
            timestamp="2026-09-06T18:00:00Z",
            hardware_info="RTX 4090",
            verifier_version="1.1",
        )

    valid_provenance = ProvenanceRecord(
        commit_sha="a1b2c3d4e5f67890",
        timestamp="2026-09-06T18:00:00Z",
        hardware_info="Local NVENC / CUDA 12.4",
        verifier_version="hawedit-1.1",
    )

    # 3. Full Accounting & Refusals Included in Denominator
    # Generate 21 proposals across 3 clean holdout episodes (18 accepted, 2 refused, 1 rejected)
    proposals: list[EvaluationProposalRecord] = []
    # ep_hold_01: 7 accepted
    for i in range(7):
        proposals.append(
            EvaluationProposalRecord(
                clip_id=f"ep1_clip_{i}",
                episode_id="ep_hold_01",
                status="accepted",
                critical_defects=0,
                preserved_visual_ratio=0.99,
            )
        )
    # ep_hold_02: 6 accepted, 1 refused
    for i in range(6):
        proposals.append(
            EvaluationProposalRecord(
                clip_id=f"ep2_clip_{i}",
                episode_id="ep_hold_02",
                status="accepted",
                critical_defects=0,
                preserved_visual_ratio=0.98,
            )
        )
    proposals.append(
        EvaluationProposalRecord(
            clip_id="ep2_clip_refused",
            episode_id="ep_hold_02",
            status="refused",
            refusal_reason="wide shot cannot fit 9:16 crop without losing chart",
            critical_defects=0,
            preserved_visual_ratio=None,
        )
    )
    # ep_hold_03: 5 accepted, 1 rejected, 1 refused
    for i in range(5):
        proposals.append(
            EvaluationProposalRecord(
                clip_id=f"ep3_clip_{i}",
                episode_id="ep_hold_03",
                status="accepted",
                critical_defects=0,
                preserved_visual_ratio=0.97,
            )
        )
    proposals.append(
        EvaluationProposalRecord(
            clip_id="ep3_clip_rejected",
            episode_id="ep_hold_03",
            status="rejected",
            critical_defects=0,
            preserved_visual_ratio=0.85,
        )
    )
    proposals.append(
        EvaluationProposalRecord(
            clip_id="ep3_clip_refused_2",
            episode_id="ep_hold_03",
            status="refused",
            refusal_reason="incomplete story question without payoff",
            critical_defects=0,
        )
    )

    with pytest.raises(UnaccountedClipsError, match="empty proposals list"):
        compute_visual_scorecard(
            provenance=valid_provenance,
            split=clean_holdout,
            proposals=[],
        )

    scorecard = compute_visual_scorecard(
        provenance=valid_provenance,
        split=clean_holdout,
        proposals=proposals,
        config=VisualScorecardConfig(min_episodes=3, min_proposed_clips=20),
    )

    # All 21 proposals are strictly accounted for
    assert scorecard.total_proposed == 21
    assert scorecard.accepted_count == 18
    assert scorecard.refusal_count == 2
    assert scorecard.rejected_count == 1
    assert scorecard.refusal_rate == pytest.approx(2 / 21, abs=1e-4)
    # First pass rate MUST be over total_proposed (18/21), NOT over (18/19)!
    assert scorecard.first_pass_rate == pytest.approx(18 / 21, abs=1e-4)
    assert scorecard.first_pass_ci_lower < scorecard.first_pass_rate < scorecard.first_pass_ci_upper
    assert scorecard.is_release_eligible is True

    # 4. Episode Clustering Prevents Pseudo-Replication
    single_cluster_proposals = [
        EvaluationProposalRecord(
            clip_id=f"solo_{i}",
            episode_id="ep_hold_01",
            status="accepted",
            critical_defects=0,
        )
        for i in range(25)
    ]
    with pytest.raises(InsufficientClustersError, match="episode cluster"):
        compute_visual_scorecard(
            provenance=valid_provenance,
            split=clean_holdout,
            proposals=single_cluster_proposals,
            config=VisualScorecardConfig(min_episodes=3, min_proposed_clips=20),
        )

    # 5. Unsupported Leadership Claims Refusal
    # Attempting to declare "number one" without competitor comparisons raises error
    with pytest.raises(UnsupportedLeadershipClaimError, match="no pre-registered competitor"):
        scorecard.evaluate_leadership_claim("Declared #1 in Kurdish Reel Generation")

    # With competitor comparisons but ci_lower not strictly > 0.50
    insufficient_comp = {
        "OpusClip": CompetitorComparison(
            competitor_name="OpusClip",
            wins=25,
            losses=25,
            ties=10,
            total=60,
            win_rate=0.50,
            ci_lower=0.375,  # <= 0.50!
            ci_upper=0.625,
        )
    }
    scorecard_with_tied_comp = compute_visual_scorecard(
        provenance=valid_provenance,
        split=clean_holdout,
        proposals=proposals,
        competitor_comparisons=insufficient_comp,
    )
    with pytest.raises(UnsupportedLeadershipClaimError, match="does not strictly exceed 0.50"):
        scorecard_with_tied_comp.evaluate_leadership_claim("market leader over OpusClip")

    # With high competitor preference but missing dual signoff
    winning_comp = {
        "OpusClip": CompetitorComparison(
            competitor_name="OpusClip",
            wins=45,
            losses=10,
            ties=5,
            total=60,
            win_rate=0.75,
            ci_lower=0.630,  # > 0.50
            ci_upper=0.842,
        )
    }
    scorecard_unsigned = compute_visual_scorecard(
        provenance=valid_provenance,
        split=clean_holdout,
        proposals=proposals,
        competitor_comparisons=winning_comp,
        signoff_owner=None,  # Missing owner signoff!
        signoff_editor="Senior Kurdish Editor",
    )
    with pytest.raises(UnsupportedLeadershipClaimError, match="dual signoff"):
        scorecard_unsigned.evaluate_leadership_claim("10/10 best in market")

    # With critical defects present, leadership claims are strictly refused regardless of scores
    defect_proposals = list(proposals)
    defect_proposals[0] = EvaluationProposalRecord(
        clip_id="ep1_clip_0",
        episode_id="ep_hold_01",
        status="accepted",
        critical_defects=1,  # Critical defect!
    )
    scorecard_defective = compute_visual_scorecard(
        provenance=valid_provenance,
        split=clean_holdout,
        proposals=defect_proposals,
        competitor_comparisons=winning_comp,
        signoff_owner="Tech Lead",
        signoff_editor="Senior Kurdish Editor",
    )
    assert scorecard_defective.is_release_eligible is False
    with pytest.raises(UnsupportedLeadershipClaimError, match="critical fidelity defect"):
        scorecard_defective.evaluate_leadership_claim("superior Kurdish performance")

    # Fully substantiated claim with zero critical defects, winning CI, and dual signoff passes
    scorecard_substantiated = compute_visual_scorecard(
        provenance=valid_provenance,
        split=clean_holdout,
        proposals=proposals,
        competitor_comparisons=winning_comp,
        signoff_owner="Tech Lead",
        signoff_editor="Senior Kurdish Editor",
    )
    # Does not raise!
    scorecard_substantiated.evaluate_leadership_claim("market leader in Kurdish short-form video")
