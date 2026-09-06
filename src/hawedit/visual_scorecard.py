"""Visual scorecard and holdout evaluation machinery.

Implements step V15 (VE-15) of the visual editor intelligence roadmap.
Produces grounded release scorecards requiring:
- current, verified provenance (git commit SHA, timestamp, hardware),
- complete accounting of all proposed clips, refusals, and rejections,
- cluster-aware confidence intervals across distinct episodes to avoid pseudo-replication,
- contamination-free holdout sets disjoint from dev/training data, and
- strict refusal of ungrounded leadership or 10/10 claims.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from hawedit.comparison_kit import wilson_score_interval

__all__ = [
    "ClusterSummary",
    "CompetitorComparison",
    "DatasetSplit",
    "EvaluationProposalRecord",
    "HoldoutContaminationError",
    "InsufficientClustersError",
    "LeakedHoldoutError",
    "ProvenanceRecord",
    "StaleEvidenceError",
    "UnaccountedClipsError",
    "UnsupportedLeadershipClaimError",
    "VisualScorecard",
    "VisualScorecardConfig",
    "VisualScorecardError",
    "assert_no_holdout_leakage",
    "compute_cluster_variance",
    "compute_visual_scorecard",
]


class VisualScorecardError(Exception):
    """Base exception for visual scorecard evaluation and validation failures."""


class LeakedHoldoutError(VisualScorecardError):
    """Raised when holdout data contains overlap with development or training data."""


HoldoutContaminationError = LeakedHoldoutError


class StaleEvidenceError(VisualScorecardError):
    """Raised when evaluation evidence is missing, unprovenanced, or stale."""


class UnaccountedClipsError(VisualScorecardError):
    """Raised when proposed clips are unaccounted for or drop refusals from the denominator."""


class InsufficientClustersError(VisualScorecardError):
    """Raised when an evaluation has too few episode clusters, causing pseudo-replication."""


class UnsupportedLeadershipClaimError(VisualScorecardError):
    """Raised when an unsupported leadership, superiority, or 10/10 claim is asserted."""


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Cryptographic and operational provenance for an evaluation run."""

    commit_sha: str
    timestamp: str
    hardware_info: str
    verifier_version: str

    def __post_init__(self) -> None:
        if not self.commit_sha or len(self.commit_sha) < 7:
            raise StaleEvidenceError("commit_sha must be a valid git commit SHA (>= 7 chars)")
        if not self.timestamp:
            raise StaleEvidenceError("timestamp cannot be empty")
        if not self.hardware_info:
            raise StaleEvidenceError("hardware_info must record the physical execution platform")
        if not self.verifier_version:
            raise StaleEvidenceError("verifier_version cannot be empty")


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    """Dataset partition representation to audit leakage between dev and holdout sets."""

    name: str
    episode_ids: frozenset[str]
    speaker_ids: frozenset[str] = frozenset()
    media_hashes: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.name:
            raise VisualScorecardError("Split name cannot be empty")
        if not self.episode_ids:
            raise VisualScorecardError("Split must contain at least one episode_id")


def assert_no_holdout_leakage(dev_split: DatasetSplit, holdout_split: DatasetSplit) -> None:
    """Verify that a holdout split has zero contamination from a dev/training split."""
    overlap_episodes = dev_split.episode_ids.intersection(holdout_split.episode_ids)
    if overlap_episodes:
        raise LeakedHoldoutError(
            f"Holdout contamination: episodes overlap between '{dev_split.name}' and "
            f"'{holdout_split.name}': {sorted(overlap_episodes)}"
        )

    if dev_split.speaker_ids and holdout_split.speaker_ids:
        overlap_speakers = dev_split.speaker_ids.intersection(holdout_split.speaker_ids)
        if overlap_speakers:
            raise LeakedHoldoutError(
                f"Holdout contamination: speakers overlap between '{dev_split.name}' and "
                f"'{holdout_split.name}': {sorted(overlap_speakers)}"
            )

    if dev_split.media_hashes and holdout_split.media_hashes:
        overlap_media = dev_split.media_hashes.intersection(holdout_split.media_hashes)
        if overlap_media:
            raise LeakedHoldoutError(
                f"Holdout contamination: media hashes overlap between '{dev_split.name}' and "
                f"'{holdout_split.name}': {sorted(overlap_media)}"
            )


@dataclass(frozen=True, slots=True)
class EvaluationProposalRecord:
    """Outcome record for one proposed clip candidate."""

    clip_id: str
    episode_id: str
    status: str  # 'accepted', 'rejected', 'refused'
    speaker_id: str | None = None
    refusal_reason: str | None = None
    critical_defects: int = 0
    human_correction_seconds: float = 0.0
    preserved_visual_ratio: float | None = None

    def __post_init__(self) -> None:
        if self.status not in {"accepted", "rejected", "refused"}:
            raise VisualScorecardError(
                f"Invalid proposal status '{self.status}'. Must be accepted, rejected, or refused."
            )
        if self.status == "refused" and not self.refusal_reason:
            raise VisualScorecardError("Refused proposal must specify refusal_reason")
        if self.critical_defects < 0:
            raise VisualScorecardError("critical_defects must be non-negative")


@dataclass(frozen=True, slots=True)
class ClusterSummary:
    """Aggregated outcome metrics for one episode cluster."""

    episode_id: str
    total_proposed: int
    accepted: int
    rejected: int
    refused: int
    critical_defects: int

    @property
    def publishable_rate(self) -> float:
        return self.accepted / self.total_proposed if self.total_proposed > 0 else 0.0


@dataclass(frozen=True, slots=True)
class CompetitorComparison:
    """Pairwise blinded human trial comparison against a competitor or human editor."""

    competitor_name: str
    wins: int
    losses: int
    ties: int
    total: int
    win_rate: float
    ci_lower: float
    ci_upper: float


@dataclass(frozen=True, slots=True)
class VisualScorecardConfig:
    """Thresholds and requirements for visual release scorecard acceptance."""

    min_episodes: int = 3
    min_proposed_clips: int = 20
    target_first_pass_rate: float = 0.95
    target_visual_relevance: float = 0.98
    max_critical_defects: int = 0


@dataclass(frozen=True, slots=True)
class VisualScorecard:
    """Release scorecard accounting for all proposals, clustering, and evidence."""

    provenance: ProvenanceRecord
    split_name: str
    total_episodes: int
    total_proposed: int
    accepted_count: int
    rejected_count: int
    refusal_count: int
    refusal_rate: float
    first_pass_rate: float
    first_pass_ci_lower: float
    first_pass_ci_upper: float
    critical_defects_total: int
    cluster_summaries: tuple[ClusterSummary, ...]
    competitor_comparisons: dict[str, CompetitorComparison] = field(default_factory=dict)
    average_visual_relevance: float | None = None
    signoff_owner: str | None = None
    signoff_editor: str | None = None

    @property
    def is_release_eligible(self) -> bool:
        """True only if critical defects are zero and all proposals are accounted for."""
        return (
            self.critical_defects_total == 0
            and self.total_proposed > 0
            and self.total_proposed
            == (self.accepted_count + self.rejected_count + self.refusal_count)
        )

    def evaluate_leadership_claim(self, claim: str) -> None:
        """Strictly refuse unsupported leadership, 'number one', or 10/10 claims."""
        normalized = claim.lower().strip()
        leadership_tokens = {
            "number one",
            "number_one",
            "#1",
            "10/10",
            "best in market",
            "market leader",
            "superior",
            "industry leading",
        }
        if not any(token in normalized for token in leadership_tokens):
            return

        # Refusal condition 1: Critical fidelity defects > 0
        if self.critical_defects_total > 0:
            raise UnsupportedLeadershipClaimError(
                f"Refused leadership claim '{claim}': {self.critical_defects_total} critical "
                "fidelity defect(s) observed in holdout evaluation."
            )

        # Refusal condition 2: Inadequate episode clusters or sample size
        if self.total_episodes < 3:
            raise UnsupportedLeadershipClaimError(
                f"Refused leadership claim '{claim}': sample has only {self.total_episodes} "
                "episode cluster(s); minimum 3 required to rule out pseudo-replication."
            )
        if self.total_proposed < 20:
            raise UnsupportedLeadershipClaimError(
                f"Refused leadership claim '{claim}': total proposed clips ({self.total_proposed}) "
                "is insufficient (< 20)."
            )

        # Refusal condition 3: First pass rate lower bound below 0.50
        if self.first_pass_ci_lower <= 0.50:
            raise UnsupportedLeadershipClaimError(
                f"Refused leadership claim '{claim}': cluster-adjusted first pass rate lower "
                f"bound ({self.first_pass_ci_lower:.3f}) does not exceed 0.50."
            )

        # Refusal condition 4: Competitor comparison checks
        if not self.competitor_comparisons:
            raise UnsupportedLeadershipClaimError(
                f"Refused leadership claim '{claim}': no pre-registered competitor comparisons."
            )

        for name, comp in self.competitor_comparisons.items():
            if comp.ci_lower <= 0.50:
                raise UnsupportedLeadershipClaimError(
                    f"Refused leadership claim '{claim}': comparison against '{name}' lower "
                    f"confidence interval ({comp.ci_lower:.3f}) does not strictly exceed 0.50."
                )

        # Refusal condition 5: Required dual signoff (owner and Kurdish editor)
        if not self.signoff_owner or not self.signoff_editor:
            raise UnsupportedLeadershipClaimError(
                f"Refused leadership claim '{claim}': requires explicit dual signoff from both "
                f"owner ({self.signoff_owner}) and Kurdish editor ({self.signoff_editor})."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provenance": {
                "commit_sha": self.provenance.commit_sha,
                "timestamp": self.provenance.timestamp,
                "hardware_info": self.provenance.hardware_info,
                "verifier_version": self.provenance.verifier_version,
            },
            "split_name": self.split_name,
            "total_episodes": self.total_episodes,
            "total_proposed": self.total_proposed,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "refusal_count": self.refusal_count,
            "refusal_rate": round(self.refusal_rate, 4),
            "first_pass_rate": round(self.first_pass_rate, 4),
            "first_pass_ci_lower": round(self.first_pass_ci_lower, 4),
            "first_pass_ci_upper": round(self.first_pass_ci_upper, 4),
            "critical_defects_total": self.critical_defects_total,
            "average_visual_relevance": (
                round(self.average_visual_relevance, 4)
                if self.average_visual_relevance is not None
                else None
            ),
            "is_release_eligible": self.is_release_eligible,
            "signoff_owner": self.signoff_owner,
            "signoff_editor": self.signoff_editor,
        }


def compute_cluster_variance(
    clusters: list[ClusterSummary], overall_p: float, total_n: int
) -> float:
    """Compute cluster-adjusted variance using ratio estimator across clusters."""
    num_clusters = len(clusters)
    if num_clusters < 2 or total_n <= 0:
        return (overall_p * (1.0 - overall_p)) / max(1, total_n)

    sum_sq_diff = 0.0
    for c in clusters:
        # Residual = observed successes - expected successes in cluster
        diff = float(c.accepted) - (overall_p * float(c.total_proposed))
        sum_sq_diff += diff * diff

    factor = float(num_clusters) / float(num_clusters - 1)
    variance = factor * (sum_sq_diff / float(total_n * total_n))
    return max(0.0, variance)


def compute_visual_scorecard(
    *,
    provenance: ProvenanceRecord,
    split: DatasetSplit,
    proposals: list[EvaluationProposalRecord],
    config: VisualScorecardConfig | None = None,
    competitor_comparisons: dict[str, CompetitorComparison] | None = None,
    signoff_owner: str | None = None,
    signoff_editor: str | None = None,
) -> VisualScorecard:
    """Compute a rigorous release scorecard accounting for all proposals and clustering."""
    cfg = config or VisualScorecardConfig()

    if not proposals:
        raise UnaccountedClipsError("Cannot compute visual scorecard with empty proposals list")

    # Map proposals by episode
    episode_proposals: dict[str, list[EvaluationProposalRecord]] = {}
    for p in proposals:
        if p.episode_id not in split.episode_ids:
            raise VisualScorecardError(
                f"Proposal clip '{p.clip_id}' references episode '{p.episode_id}' not present "
                f"in split '{split.name}'"
            )
        episode_proposals.setdefault(p.episode_id, []).append(p)

    total_episodes = len(episode_proposals)
    if total_episodes < cfg.min_episodes:
        raise InsufficientClustersError(
            f"Evaluation includes {total_episodes} episode cluster(s), but minimum "
            f"{cfg.min_episodes} required to prevent pseudo-replication"
        )

    total_proposed = len(proposals)
    if total_proposed < cfg.min_proposed_clips:
        raise UnaccountedClipsError(
            f"Total proposed clips ({total_proposed}) below minimum ({cfg.min_proposed_clips})"
        )

    # Accumulate counts
    accepted = sum(1 for p in proposals if p.status == "accepted")
    rejected = sum(1 for p in proposals if p.status == "rejected")
    refused = sum(1 for p in proposals if p.status == "refused")
    critical_defects = sum(p.critical_defects for p in proposals)

    # Strict accounting check: every clip must be either accepted, rejected, or refused
    if total_proposed != (accepted + rejected + refused):
        raise UnaccountedClipsError(
            f"Accounting mismatch: total_proposed ({total_proposed}) != "
            f"accepted ({accepted}) + rejected ({rejected}) + refused ({refused})"
        )

    # Refusal and first pass rates over TOTAL proposals (including refusals!)
    refusal_rate = refused / total_proposed
    first_pass_rate = accepted / total_proposed

    # Cluster summaries
    cluster_list: list[ClusterSummary] = []
    for ep_id, ep_props in sorted(episode_proposals.items()):
        c_acc = sum(1 for p in ep_props if p.status == "accepted")
        c_rej = sum(1 for p in ep_props if p.status == "rejected")
        c_ref = sum(1 for p in ep_props if p.status == "refused")
        c_crit = sum(p.critical_defects for p in ep_props)
        cluster_list.append(
            ClusterSummary(
                episode_id=ep_id,
                total_proposed=len(ep_props),
                accepted=c_acc,
                rejected=c_rej,
                refused=c_ref,
                critical_defects=c_crit,
            )
        )

    # Calculate cluster-adjusted confidence intervals
    cluster_var = compute_cluster_variance(cluster_list, first_pass_rate, total_proposed)
    cluster_std_err = math.sqrt(cluster_var)
    z = 1.96
    margin = z * cluster_std_err

    # Naive Wilson interval
    naive_lower, naive_upper = wilson_score_interval(first_pass_rate, total_proposed)

    # Take conservative bounds (wider interval accounting for clustering)
    ci_lower = max(0.0, min(first_pass_rate - margin, naive_lower))
    ci_upper = min(1.0, max(first_pass_rate + margin, naive_upper))

    # Visual relevance
    relevance_values = [
        p.preserved_visual_ratio for p in proposals if p.preserved_visual_ratio is not None
    ]
    avg_relevance = sum(relevance_values) / len(relevance_values) if relevance_values else None

    return VisualScorecard(
        provenance=provenance,
        split_name=split.name,
        total_episodes=total_episodes,
        total_proposed=total_proposed,
        accepted_count=accepted,
        rejected_count=rejected,
        refusal_count=refused,
        refusal_rate=refusal_rate,
        first_pass_rate=first_pass_rate,
        first_pass_ci_lower=ci_lower,
        first_pass_ci_upper=ci_upper,
        critical_defects_total=critical_defects,
        cluster_summaries=tuple(cluster_list),
        competitor_comparisons=competitor_comparisons or {},
        average_visual_relevance=avg_relevance,
        signoff_owner=signoff_owner,
        signoff_editor=signoff_editor,
    )
