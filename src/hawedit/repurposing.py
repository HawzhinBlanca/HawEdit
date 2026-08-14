"""§8.2's repurposing benchmark metrics.

    candidate Recall@20 per discovery path · human pairwise preference · temporal IoU ·
    sentence-completeness rate · misleading-edit rate · cost and wall-clock per source hour

§8.2 opens by saying why this exists at all: "No public benchmark measures Sorani video
repurposing. Your annotated set is the only ground truth that exists." Two of its sentences
do more work than the rest, and both shape this module:

**"Per-path recall is what justifies the dual-path cost. If Path B never surfaces a winner
Path A missed, collapse it."** Per-path recall is therefore not a breakdown of an aggregate —
it is the evidence behind the most expensive structural decision in §3, and `path_unique_wins`
answers the collapse question directly rather than leaving it to interpretation. §3 Stage 3
also states the asymmetric risk plainly: "The strongest Kurdish moment is often two people
sitting still while someone says something extraordinary", which only the verbal path can
find. A recall number that hides which path found what cannot see that.

**"Misleading-edit rate is the one that matters for a media organisation. An engaging clip
that misrepresents the speaker is worse than no clip."** So it is measured over what would
actually ship, not over every candidate considered — a system that generates a hundred
misleading candidates and ships none has a misleading-edit rate of zero, and that is correct.

Unmeasured is `None` throughout, as in `metrics` (D-008): a media file with no gold winner has
no recall, and 0.0 would read as total failure rather than as an absent measurement.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from hawedit.clip import DiscoveryPath

__all__ = [
    "DEFAULT_IOU_MATCH",
    "GoldCandidate",
    "RetrievedCandidate",
    "cost_per_source_hour",
    "misleading_edit_rate",
    "pairwise_preference",
    "path_unique_wins",
    "recall_at_k",
    "recall_at_k_by_path",
    "sentence_completeness_rate",
    "temporal_iou",
    "wallclock_per_source_hour",
]

# How much a retrieved candidate must overlap a gold winner to count as having found it.
# 0.5 is the usual temporal-localization convention; §8.2 sets no value — see D-020. Below
# this, a candidate shares a fragment of the moment without being the moment.
DEFAULT_IOU_MATCH: Final = 0.5


def _validate_iou_match(iou_match: float) -> float:
    """Return a finite overlap threshold that requires some actual intersection."""
    if (
        isinstance(iou_match, bool)
        or not isinstance(iou_match, int | float)
        or not 0.0 < iou_match <= 1.0
    ):
        raise ValueError(
            f"iou_match must be a finite number in (0, 1]; got {iou_match!r}. "
            "Zero or less makes disjoint spans match, and a value above one can never match."
        )
    return float(iou_match)


def _validate_k(k: int) -> int:
    """Return a valid Recall@K cutoff rather than silently treating nonsense as no recall."""
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError(f"k must be a positive integer for Recall@K; got {k!r}")
    return k


@dataclass(frozen=True, slots=True)
class GoldCandidate:
    """One human-reviewed candidate from §8.2's annotated set."""

    candidate_id: str
    media_id: str
    in_ms: int
    out_ms: int
    discovery_path: DiscoveryPath
    is_winner: bool
    misleading: bool = False

    @property
    def span(self) -> tuple[int, int]:
        return self.in_ms, self.out_ms


@dataclass(frozen=True, slots=True)
class RetrievedCandidate:
    """One candidate a system proposed, with the rank it proposed it at."""

    media_id: str
    in_ms: int
    out_ms: int
    discovery_path: DiscoveryPath
    rank: int

    @property
    def span(self) -> tuple[int, int]:
        return self.in_ms, self.out_ms


def temporal_iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Intersection over union of two time spans.

    Raises:
        ValueError: either span has no length — an interval that occupies no time cannot
            overlap anything, and silently returning 0.0 would hide the corpus bug.
    """
    for span in (a, b):
        if span[1] <= span[0]:
            raise ValueError(f"span {span} has no length")
    intersection = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = (a[1] - a[0]) + (b[1] - b[0]) - intersection
    return intersection / union if union else 0.0


def _found_winners(
    retrieved: Sequence[RetrievedCandidate],
    winners: Sequence[GoldCandidate],
    k: int,
    iou_match: float,
) -> set[str]:
    """Which gold winners appear among the top-k retrieved candidates."""
    top_k = [candidate for candidate in retrieved if candidate.rank <= k]
    return {
        winner.candidate_id
        for winner in winners
        for candidate in top_k
        if candidate.media_id == winner.media_id
        and temporal_iou(candidate.span, winner.span) >= iou_match
    }


def recall_at_k(
    retrieved: Sequence[RetrievedCandidate],
    gold: Sequence[GoldCandidate],
    k: int = 20,
    iou_match: float = DEFAULT_IOU_MATCH,
) -> float | None:
    """Share of gold winners found within the top `k` retrieved candidates.

    Returns:
        The recall, or `None` when the gold set contains no winner — a file nobody found a
        clip in measures no recall, and 0.0 would read as total failure.

    Raises:
        ValueError: `k` is not a positive integer or `iou_match` is outside `(0, 1]`.
    """
    k = _validate_k(k)
    iou_match = _validate_iou_match(iou_match)
    winners = [candidate for candidate in gold if candidate.is_winner]
    if not winners:
        return None
    return len(_found_winners(retrieved, winners, k, iou_match)) / len(winners)


def recall_at_k_by_path(
    retrieved: Sequence[RetrievedCandidate],
    gold: Sequence[GoldCandidate],
    k: int = 20,
    iou_match: float = DEFAULT_IOU_MATCH,
) -> Mapping[DiscoveryPath, float]:
    """Recall@k for each discovery path, counting only what that path retrieved.

    Every path appears in the result, including ones that found nothing: a path scoring 0.0
    is a finding, and omitting it from the report would read as "not measured".
    """
    k = _validate_k(k)
    iou_match = _validate_iou_match(iou_match)
    winners = [candidate for candidate in gold if candidate.is_winner]
    if not winners:
        return {}
    return {
        path: len(
            _found_winners(
                [c for c in retrieved if c.discovery_path in (path, DiscoveryPath.BOTH)],
                winners,
                k,
                iou_match,
            )
        )
        / len(winners)
        for path in DiscoveryPath
    }


def path_unique_wins(
    retrieved: Sequence[RetrievedCandidate],
    gold: Sequence[GoldCandidate],
    k: int = 20,
    iou_match: float = DEFAULT_IOU_MATCH,
) -> Mapping[DiscoveryPath, int]:
    """How many gold winners each path found that **no other path** found.

    This is the collapse test §8.2 states: "If Path B never surfaces a winner Path A missed,
    collapse it." A path with zero unique wins is paying for itself with nothing — and for
    the visual path that means GPU 0, a segmented 4B model, and the whole of §3's Path B.

    Every path appears in the result **when there is something to measure**. Zero is the answer
    that justifies removing a path, so a measured zero must be reported rather than absent.

    An empty mapping means *unmeasured*, matching `recall_at_k_by_path`. This used to return
    `{verbal: 0, visual: 0, both: 0}` for a gold set with no winners, which is the one thing this
    function must never say: §8.2's collapse test reads a zero here as licence to delete a path —
    GPU 0, a 4B checkpoint and the whole of §3 Stage 3 Path B — and a gold set nobody found a clip
    in has not earned that. `recall_at_k` returns `None` for exactly this case and this disagreed
    with it, so "unmeasured is None, never 0.0" held in one metric of the pair and not the other.
    D-077.
    """
    k = _validate_k(k)
    iou_match = _validate_iou_match(iou_match)
    winners = [candidate for candidate in gold if candidate.is_winner]
    if not winners:
        return {}

    per_path = {
        path: _found_winners(
            [c for c in retrieved if c.discovery_path in (path, DiscoveryPath.BOTH)],
            winners,
            k,
            iou_match,
        )
        for path in DiscoveryPath
    }
    return {
        path: len(
            found - set().union(*(other for name, other in per_path.items() if name is not path))
        )
        for path, found in per_path.items()
    }


def misleading_edit_rate(shipped: Sequence[GoldCandidate]) -> float | None:
    """Share of shipped clips a human judged to misrepresent the speaker.

    §8.2: "Misleading-edit rate is the one that matters for a media organisation. An engaging
    clip that misrepresents the speaker is worse than no clip." Measured over what ships, so
    a system that generates misleading candidates and rejects them all scores zero — which is
    the correct answer, because nothing misleading reached anyone.

    Returns:
        The rate, or `None` when nothing shipped.
    """
    if not shipped:
        return None
    return sum(1 for clip in shipped if clip.misleading) / len(shipped)


def sentence_completeness_rate(shipped_complete_flags: Sequence[bool]) -> float | None:
    """Share of shipped clips whose sentences closed (§8.2, and Kurdish invariant #2).

    Should be 1.0 in a correct system — `boundary.assert_boundary_invariant` refuses anything
    else at the render gate. Measured anyway, because a metric that can only ever report the
    expected value is how a broken gate goes unnoticed.
    """
    if not shipped_complete_flags:
        return None
    return sum(1 for complete in shipped_complete_flags if complete) / len(shipped_complete_flags)


def pairwise_preference(
    comparisons: Iterable[tuple[str, str, str | None]],
) -> Mapping[str, float]:
    """Win rate per system from human A/B comparisons.

    Each comparison is `(system_a, system_b, winner)`, where `winner` is `None` for a tie.
    Ties count half to each side rather than being discarded: a tie is evidence the two
    systems are close, and dropping it inflates whatever margin remains.

    Raises:
        ValueError: a verdict names a system that was not in the comparison.
    """
    wins: dict[str, float] = {}
    appearances: dict[str, int] = {}
    for system_a, system_b, winner in comparisons:
        if winner is not None and winner not in (system_a, system_b):
            raise ValueError(
                f"winner {winner!r} was not part of the comparison ({system_a}, {system_b})"
            )
        for system in (system_a, system_b):
            appearances[system] = appearances.get(system, 0) + 1
            wins.setdefault(system, 0.0)
        if winner is None:
            wins[system_a] += 0.5
            wins[system_b] += 0.5
        else:
            wins[winner] += 1.0
    return {system: wins[system] / appearances[system] for system in wins}


def _per_source_hour(value: float, source_hours: float, label: str) -> float:
    if source_hours <= 0:
        raise ValueError(
            f"source_hours must be positive to report {label} per source hour; zero hours "
            f"is a corpus bug, not an infinite rate."
        )
    return value / source_hours


def cost_per_source_hour(total_cost_usd: float, source_hours: float) -> float:
    """§8.2's cost metric. §3 Stage 3 budgets Path A at roughly $0.04 per source hour."""
    return _per_source_hour(total_cost_usd, source_hours, "cost")


def wallclock_per_source_hour(total_seconds: float, source_hours: float) -> float:
    """§8.2's throughput metric, in seconds of processing per hour of source."""
    return _per_source_hour(total_seconds, source_hours, "wall clock")
