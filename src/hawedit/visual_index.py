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

The real Qwen adapters live in ``qwen_visual.py`` and are composed in ``visual_pipeline.py``.
The retrieval arithmetic remains independent of model loading and is tested directly.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from typing import Final, Protocol

from hawedit.registry import resolve_role

__all__ = [
    "DECLARED_SAMPLING_FPS",
    "KEEP_MAX",
    "KEEP_MIN",
    "MAX_FRAMES_PER_WINDOW",
    "REFERENCE_FPS",
    "RETRIEVE_K",
    "TEMPORAL_PATCH_FRAMES",
    "VIDEOCHAT3_3090TI_MAX_FRAMES",
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
# Measured on the production RTX 3090 Ti with VideoChat3-4B: 8 frames succeeded at 21.57 GiB;
# 9 frames OOMed. This is a consumer capacity below §3's general Stage 2 ceiling. D-138.
VIDEOCHAT3_3090TI_MAX_FRAMES: Final = 8
REFERENCE_FPS: Final = 1.0

# The other end of the rate, and it is not §3's — it is the checkpoints'. All four §7 visual
# models ship `do_sample_frames: true` with `fps: 2`, `min_frames: 4` and
# `temporal_patch_size: 2` in `video_preprocessor_config.json`, so their processors re-sample
# whatever they are handed. Measured off `video_grid_thw` (D-060):
#
#     extracted  rate    the model read
#            64  4 fps   32
#            45  3 fps   30
#            64  1 fps   64
#
# So §3's "~1 fps" has a hard upper bound of 2: past it, frames are extracted and thrown away.
# `SceneWindow` refuses above it for the same reason it refuses below `REFERENCE_FPS` — a window
# that misreports how much of itself the model saw embeds indistinguishably from an honest one.
DECLARED_SAMPLING_FPS: Final = 2.0
_MIN_SAMPLED_FRAMES: Final = 4
TEMPORAL_PATCH_FRAMES: Final = 2

# §3 Stage 2: "Retrieve top 50 → Qwen3-VL-Reranker-2B → keep top 5–10."
RETRIEVE_K: Final = 50
KEEP_MIN: Final = 5
KEEP_MAX: Final = 10

_EMBEDDING_ROLE: Final = frozenset({"visual_embedding"})
_RERANK_ROLE: Final = frozenset({"visual_rerank"})


class VisualIndexError(RuntimeError):
    """The visual index refused something it cannot do honestly."""


def _frames_the_model_reads(duration_ms: int) -> int:
    """What a processor re-sampling at its declared rate will actually take (D-060)."""
    return max(_MIN_SAMPLED_FRAMES, round(DECLARED_SAMPLING_FPS * duration_ms / 1000))


def _max_window_ms(fps: float, max_frames: int = MAX_FRAMES_PER_WINDOW) -> int:
    """The longest window that still fits `max_frames` frames at `fps`."""
    return math.floor(max_frames * 1000 / fps)


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
        if self.fps > DECLARED_SAMPLING_FPS:
            raise ValueError(
                f"window {self.window_id} samples at {self.fps} fps, above the "
                f"{DECLARED_SAMPLING_FPS} fps every §7 visual checkpoint declares in its "
                f"`video_preprocessor_config.json`. Their processors re-sample whatever they are "
                f"handed, so a higher rate is extracted and then discarded: measured, this "
                f"window's {self.frame_count} frames would reach the model as "
                f"{_frames_the_model_reads(self.duration_ms)}. The rate is the ceiling's other "
                f"half — raising it costs ffmpeg time and buys "
                f"the model nothing. D-063, D-065."
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
    *,
    max_frames: int = MAX_FRAMES_PER_WINDOW,
) -> tuple[SceneWindow, ...]:
    """Turn Stage 0's shot cuts into windows that tile the media and fit the ceiling.

    `shot_cuts_ms` is what `ingest.detect_shots` returns: the times at which a new scene
    begins, with the file start excluded because the beginning of a file is not a cut.

    Scenes longer than the ceiling are split into equal parts rather than into a run of full
    windows plus a remainder. A 64 s window followed by a 1 s window would embed one frame as
    a whole scene, and that vector then competes for retrieval slots against vectors built
    from sixty-four.

    `max_frames` defaults to §3's `MAX_FRAMES_PER_WINDOW` and may only be lowered. It exists
    because §3's ceiling and the Path B reader's memory are in tension on real hardware:
    measured on hawapc01, `MCG-NJU/VideoChat3-4B` reads at most **8** frames per window on a
    23.99 GiB 3090 Ti, and the demand is quadratic in frames (D-138, `BLOCKED.md` #17). Planning
    windows the reader cannot read is the failure that stopped the 38-minute run; planning
    smaller ones is the only option that neither lowers §3's constant nor truncates a window at
    read time, both of which this repo refuses elsewhere.

    A lower ceiling changes what a window *is*: more of them, each seeing less context, so
    §8.2's Recall@K is then measured on a different retrieval unit than §3 describes. That is a
    real cost, recorded rather than hidden. D-143.

    Raises:
        VisualIndexError: `duration_ms` is not positive, a shot cut is invalid, or `max_frames`
            is outside `[TEMPORAL_PATCH_FRAMES, MAX_FRAMES_PER_WINDOW]`.
    """
    if isinstance(max_frames, bool) or not isinstance(max_frames, int):
        raise VisualIndexError(
            "max_frames must be an exact integer in "
            f"{TEMPORAL_PATCH_FRAMES}..{MAX_FRAMES_PER_WINDOW}, got {max_frames!r}"
        )
    if not TEMPORAL_PATCH_FRAMES <= max_frames <= MAX_FRAMES_PER_WINDOW:
        raise VisualIndexError(
            f"max_frames={max_frames} is outside {TEMPORAL_PATCH_FRAMES}.."
            f"{MAX_FRAMES_PER_WINDOW}. Above the ceiling it would exceed §3 Stage 2's published "
            f"setting; below {TEMPORAL_PATCH_FRAMES} a window cannot fill one temporal patch, so "
            f"the processor would pad it by repeating a frame that was never filmed (D-060)."
        )
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
    max_ms = _max_window_ms(fps, max_frames)
    windows: list[SceneWindow] = []
    for scene_index, (start, end) in enumerate(pairwise(boundaries)):
        scene_ms = end - start
        parts = math.ceil(scene_ms / max_ms)
        base, remainder = divmod(scene_ms, parts)
        cursor = start
        for window_index in range(parts):
            length = base + 1 if window_index < remainder else base
            window = SceneWindow(
                media_id=media_id,
                scene_index=scene_index,
                window_index=window_index,
                in_ms=cursor,
                out_ms=cursor + length,
                fps=fps,
            )
            if window.frame_count > max_frames:
                raise VisualIndexError(
                    f"planner produced {window.frame_count} frames for {window.window_id}, past "
                    f"the selected consumer capacity {max_frames}"
                )
            windows.append(window)
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
            first = next(iter(self._embeddings.values()))
            if embedding.dimension != first.dimension:
                raise VisualIndexError(
                    f"{window.window_id} has dimension {embedding.dimension}; the index holds "
                    f"{first.dimension}. Two dimensions means two models, and their scores are "
                    f"not comparable."
                )
            # Two sampling rates means two descriptions of the same kind of footage, and the
            # difference is not small. Measured on the fixture, the *same* 0–4162 ms span
            # embedded at three rates: 1 vs 2 fps sit 0.117 apart in cosine distance, 1 vs 4
            # fps 0.057, 2 vs 4 fps 0.034. Three visually distinct scenes sit 0.186–0.224
            # apart. So the rate alone accounts for up to 63% of the distance between genuinely
            # different footage, and a window can outrank a more relevant one for having been
            # sampled differently. The rate reaches the model explicitly — `video_metadata`
            # carries it (D-049) — so this is the model describing different inputs, not noise.
            #
            # `plan_scene_windows` already takes one rate for a whole media, so the honest path
            # produces a uniform index; nothing enforced it, which is the defect. §3's reference
            # is ~1 fps, and a choice to raise it for short scenes (D-052) is a choice for the
            # whole index, not per window.
            if window.fps != first.window.fps:
                raise VisualIndexError(
                    f"{window.window_id} was sampled at {window.fps} fps; the index holds "
                    f"{first.window.fps} fps. The same footage embedded at two rates lands up "
                    f"to 0.117 apart in cosine distance, against 0.186–0.224 between different "
                    f"scenes — so mixing them lets the sampling rate outweigh the content. "
                    f"Embed the whole media at one rate."
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
    # The floor was checked against `len(index)` only, so `k` walked straight past it: on a
    # 60-window index with keep=5, k=3 returned 3 survivors and no error, k=1 returned 1, k=0
    # returned an empty tuple, and k=-5 returned 5 survivors after reranking 55 windows because
    # `retrieve` slices `scored[:k]` and a negative k drops the tail instead of keeping a head.
    # Retrieving fewer candidates than the survivor count cannot produce `keep` survivors — that
    # is arithmetic, not a chosen threshold — so it is refused here rather than silently
    # shortening the slice the same way D-037 clause 4 forbids. D-102.
    if k < keep:
        raise VisualIndexError(
            f"k={k} retrieves fewer candidates than the {keep} survivors §3 Stage 2 asks for, so "
            f"the survivor slice could only ever be short. §3 fixes the retrieval depth at "
            f"{RETRIEVE_K}; a smaller k is a caller error, and a negative one silently reranks "
            f"everything except the tail. Raise k or lower keep, deliberately."
        )
    # Below the survivor floor the retrieval refuses instead of shortening — D-037 clause 4,
    # which considered "return whatever exists" and rejected it: §8.2 counts Recall@K on this
    # list, and three results in a column that says five is a number that does not mean what the
    # column says. Checked before the reranker runs, so a media too small for §3's slice costs no
    # GPU time. Restored 2026-08-08 (D-066) after it was reverted to `min(keep, len(reranked))`
    # to accommodate the three-scene fixture; a real episode is ~75 windows at 2 fps, so the
    # short-index case is the test material, not the product.
    if len(index) < keep:
        raise VisualIndexError(
            f"the index holds {len(index)} windows and {keep} survivors were asked for. §3 "
            f"Stage 2 fixes the count at {KEEP_MIN}–{KEEP_MAX}; returning fewer would put a "
            f"number in §8.2's Recall@K column that does not mean what the column says. This "
            f"media is too short for Stage 2's survivor slice — the caller decides whether to "
            f"skip the slice, and says so, rather than this function shortening it quietly."
        )
    hits = index.retrieve(query_vector, k=k)
    if not hits:
        return ()
    retrieved = {hit.window.window_id: hit for hit in hits}
    reranked = reranker.rerank(query_text, hits)

    if len(reranked) != len(hits):
        raise VisualIndexError(
            f"the reranker was given {len(hits)} hits and returned {len(reranked)}; "
            "it must score every retrieved window. On media with fewer than the configured "
            "survivor target, every available window survives, but none may disappear."
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
