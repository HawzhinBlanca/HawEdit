"""M7.1 — §8.2's repurposing benchmark metrics.

    candidate Recall@20 per discovery path · human pairwise preference · temporal IoU ·
    sentence-completeness rate · misleading-edit rate · cost and wall-clock per source hour

Two sentences from §8.2 shape this module more than the rest:

* "**Per-path recall is what justifies the dual-path cost.** If Path B never surfaces a winner
  Path A missed, collapse it." So per-path recall is not a breakdown of an aggregate — it is
  the number the architecture's most expensive decision rests on, and `path_unique_wins`
  answers the collapse question directly.
* "**Misleading-edit rate is the one that matters for a media organisation.** An engaging clip
  that misrepresents the speaker is worse than no clip." So it is measured over what would
  actually *ship*, not over all candidates.
"""

from __future__ import annotations

import pytest

from hawedit.clip import DiscoveryPath
from hawedit.repurposing import (
    DEFAULT_IOU_MATCH,
    GoldCandidate,
    RetrievedCandidate,
    cost_per_source_hour,
    misleading_edit_rate,
    pairwise_preference,
    path_unique_wins,
    recall_at_k,
    recall_at_k_by_path,
    sentence_completeness_rate,
    temporal_iou,
    wallclock_per_source_hour,
)


def gold(
    candidate_id: str,
    in_ms: int,
    out_ms: int,
    path: DiscoveryPath = DiscoveryPath.VERBAL,
    winner: bool = True,
    misleading: bool = False,
) -> GoldCandidate:
    return GoldCandidate(
        candidate_id=candidate_id,
        media_id="m1",
        in_ms=in_ms,
        out_ms=out_ms,
        discovery_path=path,
        is_winner=winner,
        misleading=misleading,
    )


def found(
    in_ms: int, out_ms: int, path: DiscoveryPath = DiscoveryPath.VERBAL, rank: int = 1
) -> RetrievedCandidate:
    return RetrievedCandidate(
        media_id="m1", in_ms=in_ms, out_ms=out_ms, discovery_path=path, rank=rank
    )


# --- temporal IoU -----------------------------------------------------------------------


def test_identical_intervals_have_full_overlap() -> None:
    assert temporal_iou((0, 1000), (0, 1000)) == 1.0


def test_disjoint_intervals_have_no_overlap() -> None:
    assert temporal_iou((0, 1000), (2000, 3000)) == 0.0


def test_touching_intervals_have_no_overlap() -> None:
    assert temporal_iou((0, 1000), (1000, 2000)) == 0.0


def test_half_overlap_scores_a_third() -> None:
    """Intersection 500, union 1500."""
    assert temporal_iou((0, 1000), (500, 1500)) == pytest.approx(1 / 3)


def test_a_zero_length_interval_is_refused() -> None:
    with pytest.raises(ValueError, match="length"):
        temporal_iou((100, 100), (0, 1000))


# --- recall -------------------------------------------------------------------------------


def test_a_retrieved_candidate_matches_a_gold_winner_by_overlap() -> None:
    winners = [gold("g1", 10_000, 20_000)]
    assert recall_at_k([found(10_500, 20_500)], winners, k=20) == 1.0


def test_a_barely_overlapping_candidate_does_not_count_as_found() -> None:
    """A clip sharing 5% of its span with the winner did not find the moment."""
    winners = [gold("g1", 10_000, 20_000)]
    assert recall_at_k([found(19_500, 29_500)], winners, k=20) == 0.0


def test_recall_only_counts_the_top_k() -> None:
    winners = [gold("g1", 10_000, 20_000)]
    assert recall_at_k([found(10_000, 20_000, rank=21)], winners, k=20) == 0.0
    assert recall_at_k([found(10_000, 20_000, rank=20)], winners, k=20) == 1.0


def test_recall_is_the_share_of_winners_found() -> None:
    winners = [gold("g1", 0, 1000), gold("g2", 5000, 6000), gold("g3", 9000, 10_000)]
    assert recall_at_k([found(0, 1000)], winners, k=20) == pytest.approx(1 / 3)


def test_non_winners_are_not_counted_as_recall() -> None:
    candidates = [gold("g1", 0, 1000, winner=True), gold("g2", 5000, 6000, winner=False)]
    assert recall_at_k([found(0, 1000), found(5000, 6000)], candidates, k=20) == 1.0


def test_recall_with_no_winners_is_none_not_zero() -> None:
    """Unmeasured is not failure. A media file with no gold winner measures no recall."""
    assert recall_at_k([found(0, 1000)], [gold("g1", 0, 1000, winner=False)], k=20) is None


def test_the_default_match_threshold_is_recorded() -> None:
    assert 0.0 < DEFAULT_IOU_MATCH < 1.0


# --- per-path recall: the number the dual-path cost rests on -----------------------------


def test_each_path_is_scored_against_every_winner_not_its_own() -> None:
    """The denominator is *all* gold winners, deliberately.

    Grading each path only against the winners it was expected to find would let both paths
    score 1.0 while each found half the moments — and §8.2 uses this number to decide
    whether a path earns its cost. Two winners, one found by each path, is 0.5 each.
    """
    winners = [
        gold("g1", 0, 1000, path=DiscoveryPath.VERBAL),
        gold("g2", 5000, 6000, path=DiscoveryPath.VISUAL),
    ]
    retrieved = [
        found(0, 1000, path=DiscoveryPath.VERBAL),
        found(5000, 6000, path=DiscoveryPath.VISUAL),
    ]
    by_path = recall_at_k_by_path(retrieved, winners, k=20)
    assert by_path[DiscoveryPath.VERBAL] == pytest.approx(0.5)
    assert by_path[DiscoveryPath.VISUAL] == pytest.approx(0.5)


def test_a_path_that_finds_everything_scores_full_recall() -> None:
    winners = [gold("g1", 0, 1000), gold("g2", 5000, 6000)]
    retrieved = [
        found(0, 1000, path=DiscoveryPath.VERBAL),
        found(5000, 6000, path=DiscoveryPath.VERBAL),
    ]
    assert recall_at_k_by_path(retrieved, winners, k=20)[DiscoveryPath.VERBAL] == 1.0


def test_a_path_that_found_nothing_scores_zero_not_absent() -> None:
    winners = [gold("g1", 0, 1000), gold("g2", 5000, 6000)]
    by_path = recall_at_k_by_path([found(0, 1000, path=DiscoveryPath.VERBAL)], winners, k=20)
    assert by_path[DiscoveryPath.VISUAL] == 0.0


def test_path_unique_wins_answers_the_collapse_question() -> None:
    """§8.2: "If Path B never surfaces a winner Path A missed, collapse it." """
    winners = [gold("g1", 0, 1000), gold("g2", 5000, 6000)]
    retrieved = [
        found(0, 1000, path=DiscoveryPath.VERBAL),
        found(5000, 6000, path=DiscoveryPath.VISUAL),
    ]
    unique = path_unique_wins(retrieved, winners, k=20)
    assert unique[DiscoveryPath.VISUAL] == 1, "the visual path found a winner verbal missed"
    assert unique[DiscoveryPath.VERBAL] == 1


def test_a_redundant_path_has_no_unique_wins() -> None:
    """Both paths find the same single winner: the visual path justified nothing."""
    winners = [gold("g1", 0, 1000)]
    retrieved = [
        found(0, 1000, path=DiscoveryPath.VERBAL),
        found(0, 1000, path=DiscoveryPath.VISUAL),
    ]
    assert path_unique_wins(retrieved, winners, k=20)[DiscoveryPath.VISUAL] == 0


def test_the_purely_verbal_moment_section_3_warns_about() -> None:
    """§3 Stage 3: "The strongest Kurdish moment is often two people sitting still while
    someone says something extraordinary." Only the verbal path finds it."""
    winners = [gold("g1", 0, 1000)]
    retrieved = [found(0, 1000, path=DiscoveryPath.VERBAL)]
    unique = path_unique_wins(retrieved, winners, k=20)
    assert unique[DiscoveryPath.VERBAL] == 1
    assert unique[DiscoveryPath.VISUAL] == 0


# --- misleading-edit rate ------------------------------------------------------------------


def test_misleading_edit_rate_is_measured_over_what_would_ship() -> None:
    """§8.2: "An engaging clip that misrepresents the speaker is worse than no clip." """
    shipped = [gold("g1", 0, 1000, misleading=True), gold("g2", 2000, 3000, misleading=False)]
    assert misleading_edit_rate(shipped) == pytest.approx(0.5)


def test_a_clean_set_has_a_zero_misleading_rate() -> None:
    assert misleading_edit_rate([gold("g1", 0, 1000)]) == 0.0


def test_misleading_edit_rate_of_nothing_shipped_is_none() -> None:
    assert misleading_edit_rate([]) is None


# --- sentence completeness ------------------------------------------------------------------


def test_sentence_completeness_rate_counts_complete_clips() -> None:
    assert sentence_completeness_rate([True, True, False, True]) == pytest.approx(0.75)


def test_a_fully_complete_set_scores_one() -> None:
    assert sentence_completeness_rate([True, True]) == 1.0


def test_sentence_completeness_of_nothing_is_none() -> None:
    assert sentence_completeness_rate([]) is None


# --- human pairwise preference ---------------------------------------------------------------


def test_pairwise_preference_counts_wins() -> None:
    result = pairwise_preference([("a", "b", "a"), ("a", "b", "a"), ("a", "b", "b")])
    assert result["a"] == pytest.approx(2 / 3)
    assert result["b"] == pytest.approx(1 / 3)


def test_ties_count_half_to_each_side() -> None:
    result = pairwise_preference([("a", "b", None), ("a", "b", "a")])
    assert result["a"] == pytest.approx(0.75)
    assert result["b"] == pytest.approx(0.25)


def test_a_verdict_naming_an_uninvolved_system_is_refused() -> None:
    with pytest.raises(ValueError, match="winner"):
        pairwise_preference([("a", "b", "c")])


def test_no_comparisons_yields_no_preferences() -> None:
    assert pairwise_preference([]) == {}


# --- cost and wall clock -----------------------------------------------------------------------


def test_cost_per_source_hour() -> None:
    assert cost_per_source_hour(total_cost_usd=0.08, source_hours=2.0) == pytest.approx(0.04)


def test_wallclock_per_source_hour() -> None:
    assert wallclock_per_source_hour(total_seconds=3600.0, source_hours=2.0) == pytest.approx(
        1800.0
    )


def test_dividing_by_no_source_hours_is_refused() -> None:
    """A per-hour figure over zero hours is not infinity, it is a corpus bug."""
    with pytest.raises(ValueError, match="source_hours"):
        cost_per_source_hour(total_cost_usd=1.0, source_hours=0.0)
    with pytest.raises(ValueError, match="source_hours"):
        wallclock_per_source_hour(total_seconds=1.0, source_hours=0.0)


# --- unmeasured is not zero, in BOTH halves of the collapse metric ------------------------
#
# `path_unique_wins` returned `{verbal: 0, visual: 0, both: 0}` for a gold set with no winners,
# while `recall_at_k` returned `None` for the same input. §8.2's collapse test reads a zero here
# as licence to delete a path, so an unmeasured zero is a decision-grade wrong number. Found by
# the 2026-08-09 adversarial pass. D-077.


def test_unique_wins_are_unmeasured_not_zero_when_no_gold_winner_exists() -> None:
    """Empty mapping, matching `recall_at_k_by_path` — not a zero for every path."""
    gold = (GoldCandidate("g1", "m", 0, 1_000, DiscoveryPath.VERBAL, is_winner=False),)
    retrieved = (RetrievedCandidate("m", 0, 1_000, DiscoveryPath.VERBAL, 1),)
    assert path_unique_wins(retrieved, gold) == {}
    assert path_unique_wins(retrieved, ()) == {}
    # The pair must agree about whether anything was measured at all.
    assert recall_at_k(retrieved, gold) is None
    assert recall_at_k_by_path(retrieved, gold) == {}


def test_a_measured_zero_is_still_reported_for_every_path() -> None:
    """The control, and the reason the fix is not `return {}` unconditionally.

    With a real winner that only the verbal path retrieved, `visual` must appear carrying 0 —
    that zero is §8.2's collapse finding and dropping it would hide the answer the metric exists
    to give.
    """
    gold = (GoldCandidate("g1", "m", 0, 1_000, DiscoveryPath.VERBAL, is_winner=True),)
    retrieved = (RetrievedCandidate("m", 0, 1_000, DiscoveryPath.VERBAL, 1),)
    wins = path_unique_wins(retrieved, gold)
    assert set(wins) == set(DiscoveryPath), f"a path went missing from a measured result: {wins}"
    assert wins[DiscoveryPath.VERBAL] == 1
    assert wins[DiscoveryPath.VISUAL] == 0


# --- a nonsense cutoff or threshold must be refused, not reported as 0.0 ------------------
#
# `k` and `iou_match` were accepted unvalidated, and both fail the same way: every match misses
# and the metric reports 0.0, which §8.2's collapse test reads as "this path found nothing".
# Measured against one gold winner retrieved exactly (IoU 1.0): iou_match=1.5 gave 0.0,
# iou_match=nan gave 0.0, k=0 gave 0.0, and iou_match=-1.0 matched candidates with no overlap.
# Found by the 2026-08-09 adversarial pass. D-080.

_METRICS = (recall_at_k, recall_at_k_by_path, path_unique_wins)


def _one_perfect_match() -> tuple[tuple[RetrievedCandidate, ...], tuple[GoldCandidate, ...]]:
    """One winner, retrieved exactly. Any honest threshold in [0, 1] must find it."""
    gold = (GoldCandidate("g1", "m", 0, 1_000, DiscoveryPath.VERBAL, is_winner=True),)
    retrieved = (RetrievedCandidate("m", 0, 1_000, DiscoveryPath.VERBAL, 1),)
    return retrieved, gold


@pytest.mark.parametrize("bad", [1.5, 2.0, -1.0, -0.001, float("nan")])
def test_an_iou_threshold_outside_zero_to_one_is_refused(bad: float) -> None:
    """Every entry point, because each was independently reachable with a bad threshold."""
    retrieved, gold = _one_perfect_match()
    for metric in _METRICS:
        with pytest.raises(ValueError, match="iou_match must be within"):
            metric(retrieved, gold, iou_match=bad)


@pytest.mark.parametrize("bad", [0, -1, -20])
def test_a_cutoff_below_one_is_refused(bad: int) -> None:
    retrieved, gold = _one_perfect_match()
    for metric in _METRICS:
        with pytest.raises(ValueError, match="k must be at least 1"):
            metric(retrieved, gold, k=bad)


def test_the_refusal_happens_even_when_there_is_nothing_to_measure() -> None:
    """The guard sits at the entry points, not in the funnel that no-winner sets skip.

    Otherwise a caller passing `k=-5` is handed `None`/`{}` — "unmeasured" — and never learns
    the cutoff was nonsense.
    """
    gold = (GoldCandidate("g1", "m", 0, 1_000, DiscoveryPath.VERBAL, is_winner=False),)
    retrieved = (RetrievedCandidate("m", 0, 1_000, DiscoveryPath.VERBAL, 1),)
    for metric in _METRICS:
        with pytest.raises(ValueError, match="k must be at least 1"):
            metric(retrieved, gold, k=-5)


@pytest.mark.parametrize("legal", [0.0, 0.5, DEFAULT_IOU_MATCH, 1.0])
def test_the_legal_threshold_boundaries_are_still_accepted(legal: float) -> None:
    """The control. A guard rejecting 0.0 or 1.0 would break honest callers.

    0.0 means "any overlap counts" and 1.0 means "exact span only"; both are defensible
    choices §8.2 does not forbid, and the perfect match must be found at every one of them.
    """
    retrieved, gold = _one_perfect_match()
    assert recall_at_k(retrieved, gold, iou_match=legal) == 1.0
    assert recall_at_k_by_path(retrieved, gold, iou_match=legal)[DiscoveryPath.VERBAL] == 1.0
    assert path_unique_wins(retrieved, gold, iou_match=legal)[DiscoveryPath.VERBAL] == 1


def test_a_cutoff_of_one_is_still_accepted() -> None:
    """The control for `k`: Recall@1 is a real question, and only k < 1 is nonsense."""
    retrieved, gold = _one_perfect_match()
    assert recall_at_k(retrieved, gold, k=1) == 1.0
