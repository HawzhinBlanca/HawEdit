"""§3 Stage 3 — dual-path candidate merge. "Union, never intersect."

§3 calls Stage 3 "the most important structural decision in the system", and the reason is a
failure mode rather than a feature:

    A purely verbal moment — no motion, no visual signal — is invisible to every local
    component in this pipeline. If the visual stage filters first, the best clip in the
    episode is gone before anything that understands Kurdish ever reads it.

So the merge's job is not to pick winners. It is to make sure nothing is lost between two
paths that cannot see each other's evidence, and to remember which path saw what — because
§8.2 measures Recall@20 *per path* and asks how many winners each path found *uniquely*, and
neither question survives a merge that forgets where a candidate came from.

Four rules are tested here harder than anything else, because each has a plausible-looking
implementation that silently destroys candidates:

* **Nothing is dropped.** Every input appears in exactly one output. Stated as a property and
  checked over generated inputs, not by example.
* **Overlap does not chain.** If verbal V1 overlaps visual X and X overlaps verbal V2 while V1
  and V2 do not overlap each other, transitive grouping would fuse all three into one
  candidate spanning more time than any of them. That is a union-find bug that looks correct
  in every small test.
* **A path never dedupes itself.** Two overlapping verbal candidates are two moments the judge
  chose to emit. Collapsing them is the merge second-guessing a path, which is not its job.
* **The span is the anchor's, not the union's.** §3 Stage 5 owns boundaries. A merge that
  widened spans would pre-empt fusion and quietly break §8.2's IoU matching.
"""

from __future__ import annotations

import random

import pytest

from hawedit.clip import DiscoveryPath, Sv6d
from hawedit.discovery import (
    Candidate,
    MergedCandidate,
    merge_candidates,
    to_retrieved,
)
from hawedit.repurposing import DEFAULT_IOU_MATCH, GoldCandidate, path_unique_wins, recall_at_k

MEDIA = "ep01"


def verbal(
    cid: str, in_ms: int, out_ms: int, rank: int = 1, score: float | None = 0.8
) -> Candidate:
    return Candidate(
        candidate_id=cid,
        media_id=MEDIA,
        in_ms=in_ms,
        out_ms=out_ms,
        path=DiscoveryPath.VERBAL,
        rank=rank,
        score=score,
    )


def visual(
    cid: str,
    in_ms: int,
    out_ms: int,
    rank: int = 1,
    score: float | None = 0.7,
    sv6d: Sv6d | None = None,
) -> Candidate:
    return Candidate(
        candidate_id=cid,
        media_id=MEDIA,
        in_ms=in_ms,
        out_ms=out_ms,
        path=DiscoveryPath.VISUAL,
        rank=rank,
        score=score,
        sv6d=sv6d,
    )


def an_sv6d() -> Sv6d:
    return Sv6d(
        subject="speaker at 00:12",
        aesthetics="high contrast at 00:12",
        camera="static at 00:12",
        editing="hard cut at 00:14",
        narrative="turn at 00:13",
        retention="hook at 00:12",
    )


# --- the headline rule: union, never intersect --------------------------------------------


def test_a_purely_verbal_candidate_survives_with_no_visual_signal() -> None:
    """§3's stated worst case: the best clip in the episode is a talking head.

    If this merge required corroboration, a moment with no motion and no visual interest — the
    single case §3 built the dual path to protect — would be filtered out by a stage that
    cannot read Kurdish.
    """
    merged = merge_candidates([verbal("v1", 1_000, 5_000)], [])
    assert len(merged) == 1
    assert merged[0].discovery_path is DiscoveryPath.VERBAL
    assert merged[0].span == (1_000, 5_000)


def test_a_purely_visual_candidate_survives_with_no_verbal_signal() -> None:
    """The other direction: a reaction or gesture the transcript has no words for."""
    merged = merge_candidates([], [visual("x1", 1_000, 5_000)])
    assert len(merged) == 1
    assert merged[0].discovery_path is DiscoveryPath.VISUAL


def test_nothing_is_ever_dropped() -> None:
    """The union property, over generated input rather than by example.

    Every candidate either anchors a merged candidate or is recorded as a source of one, and
    no candidate appears twice. A merge that lost one would still pass every hand-written test
    above.
    """
    rng = random.Random(20260807)
    for _ in range(200):
        verbals = [
            verbal(
                f"v{i}",
                start := rng.randrange(0, 60_000),
                start + rng.randrange(500, 8_000),
                rank=i + 1,
            )
            for i in range(rng.randrange(0, 6))
        ]
        visuals = [
            visual(
                f"x{i}",
                start := rng.randrange(0, 60_000),
                start + rng.randrange(500, 8_000),
                rank=i + 1,
            )
            for i in range(rng.randrange(0, 6))
        ]
        merged = merge_candidates(verbals, visuals)
        represented = [source for candidate in merged for source in candidate.sources]
        assert sorted(represented) == sorted(c.candidate_id for c in verbals + visuals)
        assert len(represented) == len(set(represented)), "a candidate was counted twice"


def test_the_merge_never_returns_only_the_intersection() -> None:
    """The one-line rule §3 states, as its own test: "Union, never intersect."."""
    merged = merge_candidates(
        [verbal("v1", 0, 2_000), verbal("v2", 30_000, 34_000)],
        [visual("x1", 100, 2_100), visual("x2", 50_000, 52_000)],
    )
    assert len(merged) == 3, f"expected the union of 4 candidates with one overlap, got {merged}"
    assert {c.discovery_path for c in merged} == {
        DiscoveryPath.BOTH,
        DiscoveryPath.VERBAL,
        DiscoveryPath.VISUAL,
    }


# --- attribution, which §8.2 depends on ---------------------------------------------------


def test_a_moment_both_paths_found_is_one_candidate_credited_to_both() -> None:
    merged = merge_candidates([verbal("v1", 1_000, 5_000)], [visual("x1", 1_200, 5_200)])
    assert len(merged) == 1
    assert merged[0].discovery_path is DiscoveryPath.BOTH
    assert set(merged[0].sources) == {"v1", "x1"}


def test_both_paths_ranks_and_scores_survive_the_merge() -> None:
    """§3: "Path A already scores its candidates. Stage 4 should add *visual* context to
    survivors, not re-derive verbal judgment. Don't pay the judge twice for the same reasoning."

    Stage 4 can only avoid re-deriving the verbal judgment if the verbal judgment is still
    attached when it gets there.
    """
    merged = merge_candidates(
        [verbal("v1", 1_000, 5_000, rank=3, score=0.91)],
        [visual("x1", 1_200, 5_200, rank=7, score=0.62)],
    )[0]
    assert (merged.verbal_rank, merged.verbal_score) == (3, 0.91)
    assert (merged.visual_rank, merged.visual_score) == (7, 0.62)


def test_a_score_that_was_never_measured_is_none_and_not_zero() -> None:
    """A 0.0 renders in a report as a measured verdict of "worthless"."""
    merged = merge_candidates([verbal("v1", 0, 2_000, score=None)], [])[0]
    assert merged.verbal_score is None
    assert merged.visual_score is None, "the visual path never saw this candidate"


def test_the_visual_paths_sv6d_survives_onto_the_merged_candidate() -> None:
    """Stage 4 adds visual context to survivors — the context has to arrive."""
    merged = merge_candidates(
        [verbal("v1", 1_000, 5_000)], [visual("x1", 1_100, 5_100, sv6d=an_sv6d())]
    )
    assert merged[0].sv6d is not None
    assert "00:12" in merged[0].sv6d.subject


def test_merged_output_feeds_section_8_2s_per_path_metrics() -> None:
    """The reason attribution is carried at all, exercised end to end.

    `recall_at_k_by_path` and `path_unique_wins` are §8.2's answer to "is the dual path
    earning its cost". Both read `discovery_path` off a retrieved candidate, so a merge that
    flattened attribution would make the most expensive structural decision in the system
    unmeasurable.
    """
    merged = merge_candidates(
        [verbal("v1", 1_000, 5_000)],
        [visual("x1", 1_100, 5_100), visual("x2", 40_000, 44_000)],
    )
    retrieved = to_retrieved(merged)
    assert {r.discovery_path for r in retrieved} == {DiscoveryPath.BOTH, DiscoveryPath.VISUAL}

    gold = [
        GoldCandidate("g1", MEDIA, 1_000, 5_000, DiscoveryPath.VERBAL, is_winner=True),
        GoldCandidate("g2", MEDIA, 40_000, 44_000, DiscoveryPath.VISUAL, is_winner=True),
    ]
    assert recall_at_k(retrieved, gold, k=20) == 1.0
    wins = path_unique_wins(retrieved, gold, k=20)
    assert wins[DiscoveryPath.VISUAL] >= 1, wins


# --- the three ways a plausible implementation destroys candidates ------------------------


def test_overlap_does_not_chain_across_a_shared_neighbour() -> None:
    """V1 overlaps X, X overlaps V2, V1 does not overlap V2.

    Transitive grouping (union-find on pairwise overlap) fuses all three into one candidate
    spanning from V1's start to V2's end — longer than any candidate any path proposed, and
    matching neither gold span under §8.2's IoU. The merge must produce two candidates.
    """
    v1, v2 = verbal("v1", 0, 4_000, rank=1), verbal("v2", 2_000, 6_000, rank=2)
    x = visual("x1", 1_000, 5_000)
    # The fixture only tests chaining if the two links hold and the shortcut does not.
    assert _iou(v1, x) >= DEFAULT_IOU_MATCH, "V1–X must be a link"
    assert _iou(x, v2) >= DEFAULT_IOU_MATCH, "X–V2 must be a link"
    assert _iou(v1, v2) < DEFAULT_IOU_MATCH, "V1–V2 must not overlap directly"

    merged = merge_candidates([v1, v2], [x])
    assert len(merged) == 2, f"chained into {len(merged)} group(s): {merged}"
    spans = {c.span for c in merged}
    assert spans == {(0, 4_000), (2_000, 6_000)}
    assert max(out - in_ for in_, out in spans) == 4_000, "a span grew beyond any input"


def test_a_path_never_dedupes_itself() -> None:
    """Two overlapping verbal candidates are two moments the judge chose to emit.

    Collapsing them is the merge overruling a path on its own output. Stage 3 unions across
    paths; it is not a ranker and not a deduplicator.
    """
    merged = merge_candidates(
        [verbal("v1", 0, 4_000, rank=1), verbal("v2", 100, 4_100, rank=2)], []
    )
    assert len(merged) == 2
    assert all(c.discovery_path is DiscoveryPath.VERBAL for c in merged)


def test_the_merged_span_is_the_verbal_anchors_not_the_union() -> None:
    """§3 Stage 5 owns boundaries. Widening here would pre-empt fusion and break §8.2 matching."""
    merged = merge_candidates([verbal("v1", 2_000, 6_000)], [visual("x1", 1_000, 6_500)])[0]
    assert merged.span == (2_000, 6_000), "the merge moved a boundary Stage 5 has not fused yet"


def test_a_visual_candidate_is_claimed_by_exactly_one_verbal_candidate() -> None:
    """Otherwise one visual hit corroborates two moments and §8.2 double-counts it."""
    merged = merge_candidates(
        [verbal("v1", 1_000, 5_000, rank=1), verbal("v2", 1_100, 5_100, rank=2)],
        [visual("x1", 1_050, 5_050)],
    )
    claimed = [c for c in merged if "x1" in c.sources]
    assert len(claimed) == 1
    assert claimed[0].sources[0] == "v1", "the lower-ranked verbal candidate should claim it"
    assert sum(1 for c in merged if c.discovery_path is DiscoveryPath.BOTH) == 1


# --- thresholds, determinism, refusals ----------------------------------------------------


def _iou(a: Candidate, b: Candidate) -> float:
    from hawedit.repurposing import temporal_iou

    return temporal_iou(a.span, b.span)


def test_a_glancing_overlap_is_not_the_same_moment() -> None:
    """Below the threshold, two candidates share a fragment without being one moment."""
    merged = merge_candidates([verbal("v1", 0, 10_000)], [visual("x1", 9_000, 19_000)])
    assert len(merged) == 2


def test_the_merge_groups_at_the_same_threshold_section_8_2_scores_at() -> None:
    """A merge that grouped at a different IoU than §8.2 matches at would measure a system
    other than the one it produced."""
    just_over = merge_candidates([verbal("v1", 0, 10_000)], [visual("x1", 3_000, 13_000)])
    assert _iou(verbal("v1", 0, 10_000), visual("x1", 3_000, 13_000)) > DEFAULT_IOU_MATCH
    assert len(just_over) == 1


def test_the_threshold_is_a_parameter_not_a_constant() -> None:
    """§8.2 tunes it against the labelled set; it is not something to guess once."""
    strict = merge_candidates(
        [verbal("v1", 0, 10_000)], [visual("x1", 1_000, 11_000)], iou_match=0.9
    )
    assert len(strict) == 2


def test_the_order_of_the_output_does_not_depend_on_the_order_of_the_input() -> None:
    """Re-running discovery must not reshuffle a candidate list a human is reviewing."""
    verbals = [verbal(f"v{i}", i * 9_000, i * 9_000 + 4_000, rank=i + 1) for i in range(5)]
    visuals = [visual(f"x{i}", i * 9_000 + 500, i * 9_000 + 4_500, rank=i + 1) for i in range(5)]
    expected = merge_candidates(verbals, visuals)
    rng = random.Random(7)
    for _ in range(20):
        shuffled_v, shuffled_x = list(verbals), list(visuals)
        rng.shuffle(shuffled_v)
        rng.shuffle(shuffled_x)
        assert merge_candidates(shuffled_v, shuffled_x) == expected


def test_candidates_from_different_media_never_merge() -> None:
    other = Candidate("x1", "ep02", 1_000, 5_000, DiscoveryPath.VISUAL, rank=1)
    merged = merge_candidates([verbal("v1", 1_000, 5_000)], [other])
    assert len(merged) == 2
    assert {c.media_id for c in merged} == {"ep01", "ep02"}


def test_an_input_candidate_cannot_claim_both_paths() -> None:
    """`BOTH` is what the merge *concludes*, never what a path reports about itself."""
    with pytest.raises(ValueError, match="BOTH"):
        Candidate("c", MEDIA, 0, 1_000, DiscoveryPath.BOTH, rank=1)


def test_a_verbal_candidate_in_the_visual_list_is_refused() -> None:
    with pytest.raises(ValueError, match="visual"):
        merge_candidates([], [verbal("v1", 0, 1_000)])


def test_a_visual_candidate_in_the_verbal_list_is_refused() -> None:
    with pytest.raises(ValueError, match="verbal"):
        merge_candidates([visual("x1", 0, 1_000)], [])


def test_a_duplicate_candidate_id_is_refused() -> None:
    """Two candidates with one id makes every per-candidate metric ambiguous."""
    with pytest.raises(ValueError, match="duplicate"):
        merge_candidates([verbal("v1", 0, 2_000), verbal("v1", 5_000, 7_000)], [])


def test_a_span_with_no_length_is_refused() -> None:
    with pytest.raises(ValueError, match="length"):
        Candidate("c", MEDIA, 1_000, 1_000, DiscoveryPath.VERBAL, rank=1)


def test_a_rank_below_one_is_refused() -> None:
    """Ranks are 1-based because §8.2's Recall@K counts them that way."""
    with pytest.raises(ValueError, match="rank"):
        Candidate("c", MEDIA, 0, 1_000, DiscoveryPath.VERBAL, rank=0)


def test_two_empty_paths_produce_nothing_rather_than_failing() -> None:
    assert merge_candidates([], []) == ()


# --- the artifact -------------------------------------------------------------------------


def test_a_merged_candidate_round_trips_through_json() -> None:
    import json

    merged = merge_candidates(
        [verbal("v1", 1_000, 5_000, rank=2, score=0.9)],
        [visual("x1", 1_100, 5_100, rank=4, score=0.5, sv6d=an_sv6d())],
    )[0]
    assert MergedCandidate.from_dict(json.loads(json.dumps(merged.to_dict()))) == merged


def test_the_serialized_form_names_the_path_for_a_human_reading_it() -> None:
    merged = merge_candidates([verbal("v1", 1_000, 5_000)], [visual("x1", 1_100, 5_100)])[0]
    assert merged.to_dict()["discovery_path"] == "both"
    assert merged.to_dict()["sources"] == ["v1", "x1"]


# --- what adversarial pass #11 found revertible (D-124) ---------------------------------


def test_rank_and_not_the_id_decides_who_claims_a_contested_candidate() -> None:
    """The existing test could not tell rank from id, because its fixture agreed with both.

    `v1` at rank 1 and `v2` at rank 2 sort the same way alphabetically, so dropping `rank` from
    the anchor ordering left the suite green. Here the two orders **disagree**: `v2` is rank 1,
    so `v2` must claim the contested visual candidate even though `v1` sorts first. §8.2's
    `path_unique_wins` credits whichever moment gets the corroboration.
    """
    merged = merge_candidates(
        [verbal("v1", 1_100, 5_100, rank=2), verbal("v2", 1_000, 5_000, rank=1)],
        [visual("x1", 1_050, 5_050)],
    )
    claimed = [c for c in merged if "x1" in c.sources]
    assert len(claimed) == 1
    assert claimed[0].sources[0] == "v2", "rank 1 claims it, not the alphabetically first id"


def test_the_output_is_ordered_by_media_then_start_then_id() -> None:
    """The promised order, on a case where the merge's natural order is a different one.

    Anchors are processed in rank order and Path B's leftovers are appended after them, so a
    visual-only candidate that *starts first* comes out last without the final sort — and the
    existing determinism test could not see it, because with every visual claimed there are no
    leftovers and the internal order already happens to be stable.
    """
    merged = merge_candidates(
        [verbal("v1", 10_000, 14_000, rank=1)],
        [visual("x1", 0, 4_000, rank=1)],
    )
    assert [c.candidate_id for c in merged] == ["x1", "v1"], (
        "a candidate that starts earlier must be listed earlier, whichever path found it"
    )
    assert [c.in_ms for c in merged] == sorted(c.in_ms for c in merged)


def test_section_8_2s_rank_is_the_better_of_the_two_paths() -> None:
    """`to_retrieved` takes `min`, and nothing pinned it.

    §8.2's Recall@K asks whether a winner appeared in the top K of what was *proposed*: a moment
    Path B ranked 2nd was available at position 2 whatever Path A thought of it. Taking the
    worse rank would move a corroborated moment down the list it is being scored against, and
    the existing test scores at k=20 where the two are indistinguishable.
    """
    merged = merge_candidates(
        [verbal("v1", 1_000, 5_000, rank=9)],
        [visual("x1", 1_050, 5_050, rank=2)],
    )
    (only,) = merged
    assert only.discovery_path is DiscoveryPath.BOTH
    assert only.verbal_rank == 9 and only.visual_rank == 2
    (retrieved,) = to_retrieved(merged)
    assert retrieved.rank == 2, "the earliest position at which either path surfaced it"


def test_the_better_rank_is_not_simply_the_verbal_one() -> None:
    """The control. Returning `verbal_rank` whenever it exists satisfies the test above only by
    accident of which number is smaller; here the verbal path is the better one."""
    merged = merge_candidates(
        [verbal("v1", 1_000, 5_000, rank=2)],
        [visual("x1", 1_050, 5_050, rank=7)],
    )
    (retrieved,) = to_retrieved(merged)
    assert retrieved.rank == 2
