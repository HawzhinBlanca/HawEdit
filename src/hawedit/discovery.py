"""§3 Stage 3 — dual-path candidate discovery. The merge half.

    **This is the most important structural decision in the system.**
    …
    **Union, never intersect.** Candidates from either path proceed.

§3 gives the reason, and it is a failure mode rather than a preference:

    A purely verbal moment — no motion, no visual signal — is invisible to every local
    component in this pipeline. If the visual stage filters first, the best clip in the
    episode is gone before anything that understands Kurdish ever reads it.

So this module does one job and refuses several adjacent ones.

**What it does:** takes what Path A (the Kurdish judge over the full normalized transcript)
and Path B (`VideoChat3-4B` over scenes, plus embedding/rerank retrieval) each proposed, and
produces one list in which nothing is lost and every candidate still says which path found it.

**What it does not do, and why each refusal matters:**

*It does not rank across paths.* Path A's score is an editorial judgment and Path B's is a
retrieval similarity. There is no defensible arithmetic between them, and inventing one would
be the mistake §3 Stage 1 warns about with published RTF figures — a number that looks
comparable and is not. `verbal_score` and `visual_score` stay separate, and either is `None`
when that path never saw the candidate. A fused ranking is a §8.2 tuning question against the
labelled set, not something to guess here.

*It does not move boundaries.* A merged candidate keeps the anchoring candidate's span, never
the union of the spans that agreed. §3 Stage 5 owns boundary fusion; widening here would
pre-empt it and would quietly break §8.2's IoU matching against gold.

*It does not dedupe within a path.* Two overlapping candidates from Path A are two moments the
judge chose to emit. Collapsing them is this module overruling a path on its own output.

*It does not chain overlaps.* Grouping by transitive closure — V1 overlaps X, X overlaps V2,
therefore all three are one moment — produces a candidate longer than anything any path
proposed. Each merged candidate here is anchored on a real verbal candidate and contains only
candidates that overlap **that anchor** directly.

Both producers now exist and meet here. Path A still requires an authorized Gemini/Vertex route;
Path B is locally composed behind bounded Qwen survivors. This module remains deliberately
ignorant of either adapter and merges only validated ``Candidate`` values.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from hawedit.clip import DiscoveryPath, Sv6d
from hawedit.repurposing import (
    DEFAULT_IOU_MATCH,
    RetrievedCandidate,
    _validate_iou_match,
    temporal_iou,
)

__all__ = [
    "Candidate",
    "MergedCandidate",
    "merge_candidates",
    "to_retrieved",
]


@dataclass(frozen=True, slots=True)
class Candidate:
    """One moment a single path proposed.

    `path` is `VERBAL` or `VISUAL` — never `BOTH`. `BOTH` is what the merge *concludes* about
    a moment two paths independently found; a path reporting it about its own output would be
    claiming knowledge of the other path it does not have.
    """

    candidate_id: str
    media_id: str
    in_ms: int
    out_ms: int
    path: DiscoveryPath
    rank: int
    score: float | None = None
    sv6d: Sv6d | None = None

    def __post_init__(self) -> None:
        if self.path is DiscoveryPath.BOTH:
            raise ValueError(
                f"candidate {self.candidate_id!r} claims DiscoveryPath.BOTH. That is the "
                f"merge's conclusion about a moment two paths found independently, not "
                f"something one path can report about itself (§3 Stage 3)."
            )
        if self.out_ms <= self.in_ms:
            raise ValueError(
                f"candidate {self.candidate_id!r} spans {self.in_ms}..{self.out_ms}, which has "
                f"no length. A moment that occupies no time cannot overlap anything."
            )
        if self.rank < 1:
            raise ValueError(
                f"candidate {self.candidate_id!r} has rank {self.rank}; ranks are 1-based "
                f"because §8.2 counts Recall@K that way."
            )

    @property
    def span(self) -> tuple[int, int]:
        return self.in_ms, self.out_ms


@dataclass(frozen=True, slots=True)
class MergedCandidate:
    """One moment after the union, carrying which path found it and what each path said.

    `sources` lists the input candidate ids that became this one, verbal first. It is what
    makes the union auditable: every input id appears in exactly one merged candidate's
    `sources`, so "nothing was dropped" is a checkable statement rather than a hope.
    """

    candidate_id: str
    media_id: str
    in_ms: int
    out_ms: int
    discovery_path: DiscoveryPath
    sources: tuple[str, ...]
    verbal_rank: int | None = None
    visual_rank: int | None = None
    verbal_score: float | None = None
    visual_score: float | None = None
    sv6d: Sv6d | None = None

    @property
    def span(self) -> tuple[int, int]:
        return self.in_ms, self.out_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "media_id": self.media_id,
            "in_ms": self.in_ms,
            "out_ms": self.out_ms,
            "discovery_path": self.discovery_path.value,
            "sources": list(self.sources),
            "verbal_rank": self.verbal_rank,
            "visual_rank": self.visual_rank,
            "verbal_score": self.verbal_score,
            "visual_score": self.visual_score,
            "sv6d": self.sv6d.to_dict() if self.sv6d else None,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> MergedCandidate:
        raw_sv6d = data.get("sv6d")
        return MergedCandidate(
            candidate_id=data["candidate_id"],
            media_id=data["media_id"],
            in_ms=data["in_ms"],
            out_ms=data["out_ms"],
            discovery_path=DiscoveryPath(data["discovery_path"]),
            sources=tuple(data["sources"]),
            verbal_rank=data.get("verbal_rank"),
            visual_rank=data.get("visual_rank"),
            verbal_score=data.get("verbal_score"),
            visual_score=data.get("visual_score"),
            sv6d=Sv6d(**raw_sv6d) if raw_sv6d else None,
        )


def _assert_path(candidates: Sequence[Candidate], expected: DiscoveryPath) -> None:
    wrong = [c.candidate_id for c in candidates if c.path is not expected]
    if wrong:
        raise ValueError(
            f"the {expected.value} list contains candidates from the other path: {wrong}. "
            f"§8.2 measures Recall@K per path, so a candidate filed under the wrong one is "
            f"credited to a path that never found it."
        )


def _assert_unique(candidates: Iterable[Candidate]) -> None:
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.candidate_id in seen:
            raise ValueError(
                f"duplicate candidate id {candidate.candidate_id!r}: every per-candidate "
                f"figure in §8.2 would be ambiguous about which one it described."
            )
        seen.add(candidate.candidate_id)


def merge_candidates(
    verbal: Sequence[Candidate],
    visual: Sequence[Candidate],
    iou_match: float = DEFAULT_IOU_MATCH,
) -> tuple[MergedCandidate, ...]:
    """Union Path A and Path B, keeping per-path attribution (§3 Stage 3).

    A verbal and a visual candidate are treated as the same moment when their temporal IoU
    reaches `iou_match`. Verbal candidates claim in rank order and each visual candidate is
    claimed at most once — otherwise one visual hit corroborates two moments and §8.2's
    `path_unique_wins` double-counts it. Anything unclaimed proceeds on its own.

    Args:
        iou_match: defaults to §8.2's own matching threshold. That default is a decision, not
            a convenience: grouping at one threshold while §8.2 scores at another would
            measure a system other than the one this produced. §8.2 tunes it against the
            labelled set (`BLOCKED.md` #1), and it is a parameter so that tuning is possible.

    Returns:
        Every input, in a stable order (media, then start, then id). Never fewer.

    Raises:
        ValueError: `iou_match` is outside `(0, 1]`, a candidate is in the wrong path's
            list, or two candidates share an id.
    """
    iou_match = _validate_iou_match(iou_match)
    _assert_path(verbal, DiscoveryPath.VERBAL)
    _assert_path(visual, DiscoveryPath.VISUAL)
    _assert_unique([*verbal, *visual])

    # Rank order decides who claims a contested visual candidate; id breaks ties so a
    # re-run never reshuffles a list someone is reviewing.
    anchors = sorted(verbal, key=lambda c: (c.rank, c.candidate_id))
    unclaimed = {c.candidate_id: c for c in visual}
    merged: list[MergedCandidate] = []

    for anchor in anchors:
        # Overlap is measured against the anchor only. Comparing against a growing group is
        # what lets V1~X~V2 chain into one span longer than anything either path proposed.
        partners = sorted(
            (
                candidate
                for candidate in unclaimed.values()
                if candidate.media_id == anchor.media_id
                and temporal_iou(candidate.span, anchor.span) >= iou_match
            ),
            key=lambda c: (c.rank, c.candidate_id),
        )
        partner = partners[0] if partners else None
        if partner is not None:
            del unclaimed[partner.candidate_id]

        merged.append(
            MergedCandidate(
                candidate_id=anchor.candidate_id,
                media_id=anchor.media_id,
                # The anchor's span, not the union: §3 Stage 5 fuses boundaries, and a merge
                # that widened them would decide something it has no evidence for.
                in_ms=anchor.in_ms,
                out_ms=anchor.out_ms,
                discovery_path=(
                    DiscoveryPath.BOTH if partner is not None else DiscoveryPath.VERBAL
                ),
                sources=(anchor.candidate_id,)
                + ((partner.candidate_id,) if partner is not None else ()),
                verbal_rank=anchor.rank,
                visual_rank=partner.rank if partner is not None else None,
                verbal_score=anchor.score,
                visual_score=partner.score if partner is not None else None,
                sv6d=partner.sv6d if partner is not None else anchor.sv6d,
            )
        )

    # Whatever Path B found alone. This is the half §3's warning is *not* about, and it is
    # equally unfiltered: a reaction the transcript has no words for is still a candidate.
    for leftover in unclaimed.values():
        merged.append(
            MergedCandidate(
                candidate_id=leftover.candidate_id,
                media_id=leftover.media_id,
                in_ms=leftover.in_ms,
                out_ms=leftover.out_ms,
                discovery_path=DiscoveryPath.VISUAL,
                sources=(leftover.candidate_id,),
                visual_rank=leftover.rank,
                visual_score=leftover.score,
                sv6d=leftover.sv6d,
            )
        )

    return tuple(sorted(merged, key=lambda c: (c.media_id, c.in_ms, c.candidate_id)))


def to_retrieved(merged: Sequence[MergedCandidate]) -> tuple[RetrievedCandidate, ...]:
    """Bridge to §8.2's metrics, preserving which path found each candidate.

    Rank is the better of the two paths' own ranks — the earliest position at which any path
    surfaced this moment — because §8.2's Recall@K asks whether a winner appeared in the top K
    of what was proposed, and a moment Path B ranked 2nd was available at position 2 whatever
    Path A thought of it. The per-path ranks stay on the `MergedCandidate` for anything that
    needs to ask a narrower question.
    """
    return tuple(
        RetrievedCandidate(
            media_id=candidate.media_id,
            in_ms=candidate.in_ms,
            out_ms=candidate.out_ms,
            discovery_path=candidate.discovery_path,
            rank=min(r for r in (candidate.verbal_rank, candidate.visual_rank) if r is not None),
        )
        for candidate in merged
    )
