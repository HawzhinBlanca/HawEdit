"""§3 Stage 2 — the visual index. The seam `Qwen3-VL-Embedding-2B` will plug into.

§3 Stage 2 gives the visual half of the index in four sentences:

    **Visual:** `Qwen3-VL-Embedding-2B`, one embedding per scene. Reference settings run
    ~1 fps with a maximum of 64 frames, so segment before embedding. Retrieve top 50 →
    `Qwen3-VL-Reranker-2B` → keep top 5–10.

Every one of those is a *silent* failure when it is broken, which is why they are arithmetic
here rather than prose in a docstring:

*One embedding per scene, at ~1 fps, max 64 frames.* A 180-second scene handed to a 64-frame
embedder is sampled at 0.36 fps. The vector that comes back has the right dimension, the right
norm, and no way to say that it saw a third of the frames the reference settings describe.
Nothing downstream can detect it. So `SceneWindow` refuses to exist above the ceiling and
`plan_scene_windows` splits scenes to stay under it — segmentation is not an optimisation here,
it is the only way the two settings can both hold.

*Cover the media.* A gap between windows is footage no visual query can ever retrieve. §3
Stage 3 unions the two discovery paths precisely so that no moment is invisible to the whole
system; a hole in this plan makes a moment invisible to Path B, and reports nothing.

*Top 50 → rerank → keep 5–10.* Reranking something other than the retrieved top 50 — a
pre-filtered set, everything, ten — produces numbers that look the same and mean something
else. The counts are checked, and so is the identity of what the reranker was handed.

The models are `BLOCKED.md` #2 (GPU) and #6 (weights unreachable). This module is built and
tested ahead of them, as `discovery.py` and `judge.py` were: landing the embedder is a matter
of producing `VisualEmbedding`s, and landing the reranker is a matter of satisfying
`VisualReranker`. The retrieval arithmetic in between needs no weights and is tested directly.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from typing import Final, Protocol

from hawedit.registry import resolve_role

__all__ = [
    "KEEP_MAX",
    "KEEP_MIN",
    "MAX_FRAMES_PER_WINDOW",
    "REFERENCE_FPS",
    "RETRIEVE_K",
    "RerankedHit",
    "SceneWindow",
    "VisualEmbedding",
    "VisualHit",
    "VisualIndex",
    "VisualIndexError",
    "VisualReranker",
    "assert_window_coverage",
    "plan_scene_windows",
    "rerank_and_keep",
]

# §3 Stage 2, verbatim: "Reference settings run ~1 fps with a maximum of 64 frames".
MAX_FRAMES_PER_WINDOW: Final = 64
REFERENCE_FPS: Final = 1.0

# §3 Stage 2: "Retrieve top 50 → Qwen3-VL-Reranker-2B → keep top 5–10."
RETRIEVE_K: Final = 50
KEEP_MIN: Final = 5
KEEP_MAX: Final = 10

_EMBEDDING_ROLE: Final = frozenset({"visual_embedding"})
_RERANK_ROLE: Final = frozenset({"visual_rerank"})


class VisualIndexError(RuntimeError):
    """The visual index refused something it cannot do honestly."""


def _max_window_ms(fps: float) -> int:
    """The longest window that still fits 64 frames at `fps`."""
    return math.floor(MAX_FRAMES_PER_WINDOW * 1000 / fps)


@dataclass(frozen=True, slots=True)
class SceneWindow:
    """A stretch of one scene short enough to embed at the reference settings.

    A scene shorter than the ceiling is one window; a longer one becomes several. `fps` is
    carried on the window rather than assumed by the caller because it is the *other* half of
    the ceiling — 64 frames is only the published setting when it is 64 frames of one second
    each, and a window that quietly lowered the rate to fit would satisfy the count while
    describing different footage.
    """

    media_id: str
    scene_index: int
    window_index: int
    in_ms: int
    out_ms: int
    fps: float = REFERENCE_FPS

    def __post_init__(self) -> None:
        if self.fps < REFERENCE_FPS:
            raise ValueError(
                f"window {self.window_id} samples at {self.fps} fps, below §3 Stage 2's "
                f"reference {REFERENCE_FPS} fps. Lowering the rate is how a long scene fits "
                f"under the 64-frame ceiling without being segmented, and the resulting "
                f"embedding is indistinguishable from an honest one. Split the scene instead."
            )
        if self.out_ms <= self.in_ms:
            raise ValueError(
                f"window {self.window_id} spans {self.in_ms}..{self.out_ms}, which has no "
                f"length. There is nothing to embed."
            )
        if self.scene_index < 0:
            raise ValueError(f"scene_index must be >= 0, got {self.scene_index}")
        if self.window_index < 0:
            raise ValueError(f"window_index must be >= 0, got {self.window_index}")
        if self.frame_count > MAX_FRAMES_PER_WINDOW:
            raise ValueError(
                f"window {self.window_id} is {self.duration_ms} ms, which is "
                f"{self.frame_count} frames at {self.fps} fps — past §3 Stage 2's maximum of "
                f"{MAX_FRAMES_PER_WINDOW}. §3 answers this in the same sentence: 'segment "
                f"before embedding'."
            )

    @property
    def window_id(self) -> str:
        return f"{self.media_id}:s{self.scene_index}:w{self.window_index}"

    @property
    def duration_ms(self) -> int:
        return self.out_ms - self.in_ms

    @property
    def frame_count(self) -> int:
        """Frames sampled across this window at `fps` — 64 s at 1 fps is exactly 64."""
        return math.ceil(self.duration_ms * self.fps / 1000)

    @property
    def span(self) -> tuple[int, int]:
        return self.in_ms, self.out_ms

    def to_dict(self) -> dict[str, object]:
        """§1: what one stage hands the next is JSON-serialisable data.

        `frame_count` is derived, and is written out anyway: it is the number the 64-frame
        ceiling is about, and a reader of the report should not have to redo the arithmetic
        to see whether a window is legal.
        """
        return {
            "window_id": self.window_id,
            "media_id": self.media_id,
            "scene_index": self.scene_index,
            "window_index": self.window_index,
            "in_ms": self.in_ms,
            "out_ms": self.out_ms,
            "fps": self.fps,
            "frame_count": self.frame_count,
        }


def plan_scene_windows(
    media_id: str,
    duration_ms: int,
    shot_cuts_ms: Sequence[int],
    fps: float = REFERENCE_FPS,
) -> tuple[SceneWindow, ...]:
    """Turn Stage 0's shot cuts into windows that tile the media and fit the ceiling.

    `shot_cuts_ms` is what `ingest.detect_shots` returns: the times at which a new scene
    begins, with the file start excluded because the beginning of a file is not a cut.

    Scenes longer than the ceiling are split into equal parts rather than into a run of full
    windows plus a remainder. A 64 s window followed by a 1 s window would embed one frame as
    a whole scene, and that vector then competes for retrieval slots against vectors built
    from sixty-four.
    """
    if duration_ms <= 0:
        raise VisualIndexError(f"media duration must be positive, got {duration_ms} ms")

    seen: set[int] = set()
    for cut in shot_cuts_ms:
        if cut <= 0:
            raise VisualIndexError(
                f"shot cut at {cut} ms. The beginning of a file is not a cut — "
                f"`ingest.detect_shots` already drops it, so a 0 here means raw scene starts "
                f"were passed instead of cuts."
            )
        if cut >= duration_ms:
            raise VisualIndexError(
                f"shot cut at {cut} ms is at or past the media duration of {duration_ms} ms"
            )
        if cut in seen:
            raise VisualIndexError(f"shot cut at {cut} ms appears twice")
        seen.add(cut)

    boundaries = [0, *sorted(seen), duration_ms]
    max_ms = _max_window_ms(fps)
    windows: list[SceneWindow] = []
    for scene_index, (start, end) in enumerate(pairwise(boundaries)):
        scene_ms = end - start
        parts = math.ceil(scene_ms / max_ms)
        base, remainder = divmod(scene_ms, parts)
        cursor = start
        for window_index in range(parts):
            length = base + 1 if window_index < remainder else base
            windows.append(
                SceneWindow(
                    media_id=media_id,
                    scene_index=scene_index,
                    window_index=window_index,
                    in_ms=cursor,
                    out_ms=cursor + length,
                    fps=fps,
                )
            )
            cursor += length

    plan = tuple(windows)
    # The planner checking its own output is not redundant with the tests: this is the one
    # place the arithmetic above can be wrong in a way that produces a plausible plan.
    assert_window_coverage(plan, media_id=media_id, duration_ms=duration_ms)
    return plan


def assert_window_coverage(windows: Sequence[SceneWindow], media_id: str, duration_ms: int) -> None:
    """Refuse a window plan that does not cover `[0, duration_ms)` exactly once.

    Separate from `plan_scene_windows` on purpose. A plan can reach the embedder having been
    written, stored and read back as JSON, or assembled by a caller that had its own reasons;
    this is the net under all of those, the way `assert_boundary_invariant` is the net under
    boundaries that did not come from `fuse_boundary`.
    """
    if not windows:
        raise VisualIndexError(
            f"no windows for {media_id!r}: {duration_ms} ms of media, none of it embeddable"
        )
    foreign = {w.media_id for w in windows} - {media_id}
    if foreign:
        raise VisualIndexError(
            f"window plan for media {media_id!r} contains windows from {sorted(foreign)!r}"
        )
    ordered = sorted(windows, key=lambda w: (w.in_ms, w.out_ms))
    if ordered[0].in_ms != 0:
        raise VisualIndexError(
            f"window plan starts at {ordered[0].in_ms} ms; the first {ordered[0].in_ms} ms of "
            f"{media_id!r} would be invisible to every visual query"
        )
    for previous, nxt in pairwise(ordered):
        if nxt.in_ms > previous.out_ms:
            raise VisualIndexError(
                f"gap of {nxt.in_ms - previous.out_ms} ms between {previous.window_id} "
                f"(ends {previous.out_ms}) and {nxt.window_id} (starts {nxt.in_ms}) — footage "
                f"no visual query can reach"
            )
        if nxt.in_ms < previous.out_ms:
            raise VisualIndexError(
                f"overlap of {previous.out_ms - nxt.in_ms} ms between {previous.window_id} "
                f"and {nxt.window_id}; the same footage would be embedded twice and compete "
                f"with itself for retrieval slots"
            )
    if ordered[-1].out_ms != duration_ms:
        raise VisualIndexError(
            f"window plan ends at {ordered[-1].out_ms} ms but the media is {duration_ms} ms"
        )


@dataclass(frozen=True, slots=True)
class VisualEmbedding:
    """One scene window as `Qwen3-VL-Embedding-2B` sees it.

    The vector checks are not defensive noise. A NaN component makes every comparison against
    this scene `False`, so it sinks below everything in every query, permanently and without a
    trace. A zero vector has no direction at all: cosine similarity against it is undefined,
    and the convenient answer — 0.0 — would be a *measurement this system does not have*
    dressed as one it does.
    """

    window: SceneWindow
    vector: tuple[float, ...]
    model_id: str

    def __post_init__(self) -> None:
        resolve_role(self.model_id, _EMBEDDING_ROLE, "the visual embedding model")
        if not self.vector:
            raise ValueError(f"embedding for {self.window.window_id} is empty")
        if not all(math.isfinite(v) for v in self.vector):
            raise ValueError(
                f"embedding for {self.window.window_id} has a non-finite component. A NaN "
                f"compares False against everything, so this scene would rank last in every "
                f"query for the rest of the media's life without reporting anything."
            )
        if _norm(self.vector) == 0.0:
            raise ValueError(
                f"embedding for {self.window.window_id} is the zero vector: it has no "
                f"direction, so its similarity to anything is undefined rather than 0.0"
            )

    @property
    def dimension(self) -> int:
        return len(self.vector)


@dataclass(frozen=True, slots=True)
class VisualHit:
    """One window retrieved by embedding similarity, before reranking."""

    window: SceneWindow
    similarity: float
    rank: int

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError(f"rank is 1-based (§8.2 counts Recall@K that way), got {self.rank}")


@dataclass(frozen=True, slots=True)
class RerankedHit:
    """One window after `Qwen3-VL-Reranker-2B`, carrying where it stood before.

    `retrieval_similarity` is the score retrieval gave this window, carried through unchanged.
    It is what makes "did reranking change anything?" a question §8.2 can answer; a reranker
    that supplies its own number has erased the comparison while looking identical.
    """

    window: SceneWindow
    retrieval_similarity: float
    rerank_score: float
    rank: int
    model_id: str

    def __post_init__(self) -> None:
        resolve_role(self.model_id, _RERANK_ROLE, "the visual reranker")
        if self.rank < 1:
            raise ValueError(f"rank is 1-based (§8.2 counts Recall@K that way), got {self.rank}")


class VisualReranker(Protocol):
    """`Qwen3-VL-Reranker-2B`'s interface (`BLOCKED.md` #2, #6)."""

    def rerank(self, query: str, hits: Sequence[VisualHit]) -> tuple[RerankedHit, ...]: ...


def _norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(v * v for v in vector))


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True)) / (_norm(a) * _norm(b))


class VisualIndex:
    """The embeddings for one media, and similarity search over them.

    Scoped to one media on purpose. Retrieval across an archive is a different question with
    different arithmetic, and mixing two videos in one index would let a scene from another
    episode outrank every scene in this one without anything saying so.
    """

    def __init__(self, media_id: str) -> None:
        self.media_id = media_id
        self._embeddings: dict[str, VisualEmbedding] = {}

    def __len__(self) -> int:
        return len(self._embeddings)

    def add(self, embedding: VisualEmbedding) -> None:
        window = embedding.window
        if window.media_id != self.media_id:
            raise VisualIndexError(
                f"{window.window_id} belongs to media {window.media_id!r}, not {self.media_id!r}"
            )
        if window.window_id in self._embeddings:
            raise VisualIndexError(
                f"{window.window_id} is already in the index. §3 Stage 2 is one embedding per "
                f"scene window; a second one would give that footage two chances to be "
                f"retrieved."
            )
        if self._embeddings:
            existing = next(iter(self._embeddings.values())).dimension
            if embedding.dimension != existing:
                raise VisualIndexError(
                    f"{window.window_id} has dimension {embedding.dimension}; the index holds "
                    f"{existing}. Two dimensions means two models, and their scores are not "
                    f"comparable."
                )
        self._embeddings[window.window_id] = embedding

    def add_all(self, embeddings: Iterable[VisualEmbedding]) -> None:
        for embedding in embeddings:
            self.add(embedding)

    def retrieve(self, query: Sequence[float], k: int = RETRIEVE_K) -> tuple[VisualHit, ...]:
        """The top `k` windows by cosine similarity, ranked 1-based and densely."""
        if not all(math.isfinite(v) for v in query):
            raise VisualIndexError("query embedding has a non-finite component")
        if _norm(query) == 0.0:
            raise VisualIndexError(
                "query embedding is the zero vector: it has no direction, so its similarity "
                "to every scene is undefined rather than 0.0"
            )
        if not self._embeddings:
            return ()
        dimension = next(iter(self._embeddings.values())).dimension
        if len(query) != dimension:
            raise VisualIndexError(f"query has dimension {len(query)}; the index holds {dimension}")
        scored = [
            (_cosine(query, embedding.vector), embedding.window)
            for embedding in self._embeddings.values()
        ]
        # Ties broken by time, so two identical scenes cannot swap places between runs —
        # §8.2 counts Recall@K on exactly this order.
        scored.sort(key=lambda pair: (-pair[0], pair[1].in_ms, pair[1].window_id))
        return tuple(
            VisualHit(window=window, similarity=similarity, rank=rank)
            for rank, (similarity, window) in enumerate(scored[:k], start=1)
        )


def rerank_and_keep(
    index: VisualIndex,
    query_vector: Sequence[float],
    query_text: str,
    reranker: VisualReranker,
    keep: int,
    k: int = RETRIEVE_K,
) -> tuple[RerankedHit, ...]:
    """§3 Stage 2's retrieval pipeline: retrieve top `k`, rerank, keep `keep`.

    The reranker is handed exactly what retrieval returned. It may reorder and it may score;
    it may not add a window, drop below the survivor count, return one twice, or restate the
    retrieval score it was given. Each of those produces output of the right type and the
    right length, which is the only reason they are worth checking here.
    """
    if not KEEP_MIN <= keep <= KEEP_MAX:
        raise VisualIndexError(
            f"keep={keep} is outside §3 Stage 2's survivor range of {KEEP_MIN}–{KEEP_MAX}"
        )
    if len(index) < keep:
        raise VisualIndexError(
            f"the index holds {len(index)} windows and {keep} survivors were asked for. "
            f"Returning {len(index)} would put a number into §8.2's Recall@K that does not "
            f"mean what the column says; lower the source's ambition, not the count silently."
        )

    hits = index.retrieve(query_vector, k=k)
    retrieved = {hit.window.window_id: hit for hit in hits}
    reranked = reranker.rerank(query_text, hits)

    if len(reranked) < keep:
        raise VisualIndexError(
            f"the reranker was given {len(hits)} hits and returned {len(reranked)}; "
            f"{keep} survivors were asked for"
        )
    seen: set[str] = set()
    for hit in reranked:
        window_id = hit.window.window_id
        if window_id not in retrieved:
            raise VisualIndexError(
                f"the reranker returned {window_id}, which is not among the {len(hits)} "
                f"windows it was given. A reranker orders what it is handed; a window that "
                f"was not retrieved has no retrieval score and no place in Recall@K."
            )
        if window_id in seen:
            raise VisualIndexError(f"the reranker returned {window_id} twice")
        seen.add(window_id)
        expected = retrieved[window_id].similarity
        if not math.isclose(hit.retrieval_similarity, expected, rel_tol=1e-9, abs_tol=1e-12):
            raise VisualIndexError(
                f"{window_id} carries retrieval_similarity {hit.retrieval_similarity} but "
                f"retrieval scored it {expected}. That field is evidence of where the window "
                f"stood before reranking, carried through, never restated."
            )

    # Ranks are renumbered densely over the survivors so that Recall@K counts positions in
    # what actually ships, not positions in a list that was cut afterwards.
    return tuple(
        replace(hit, rank=position) for position, hit in enumerate(reranked[:keep], start=1)
    )
