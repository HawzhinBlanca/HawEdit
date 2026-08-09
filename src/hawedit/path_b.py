"""§3 Stage 3 Path B — `VideoChat3-4B` over scenes. The seam, built ahead of the weights.

    **Path B — visual.** `VideoChat3-4B` over scenes, plus embedding/rerank retrieval. Finds
    reactions, gestures, action, scene changes, non-verbal beats.

    **Union, never intersect.** Candidates from either path proceed.

    **Prompt schema — SV6D.** Use the six-dimension structure from the Leum-VL paper as your
    output schema, applied to models you actually run: `subject · aesthetics · camera language ·
    editing · narrative · retention`. Every label must cite a timestamp. Reject output where a
    claim has no timeline evidence.

    **VideoChat3-4B notes:** … Segmentation is mandatory: the authors report ~17.7 GB at 256
    frames and ~26.7 GB at 512.

Path A (`path_a.py`) sends the whole transcript in one call and refuses to send a subset. Path
B is the mirror: it reads *scenes*, one reading each, and its refusals are about the two ways a
visual reader silently produces something that looks right.

**The frame budget is a refusal, not a hope.** §3 calls segmentation mandatory and gives the
numbers it is mandatory because of. The budget governs each model call, not the duration of an
episode: windows are packed deterministically into calls of at most 256 frames. Treating the
episode total as one call made every sufficiently long source impossible despite segmentation.

**A timestamp is not evidence unless it points at the scene.** `Sv6d` has always required each
label to cite a time, and could only require that, since the type does not know which scene it
belongs to. `speaker at 9999s` on a twelve-second scene satisfies it: two and three-quarter
hours away, regex matched, claim anchored to a moment the model was never shown.
`assert_sv6d_within_window` closes it and every `SceneReading` runs through it.

What this module does *not* do is rank against Path A, dedupe across paths, or widen a span.
`discovery.py` owns the union and §3 Stage 5 owns boundaries; a candidate here spans exactly
the window it was read from.

The real model adapter is ``video_reader.py``; ``visual_pipeline.py`` ensures this contract is
invoked only for Qwen-reranked survivors.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from hawedit.clip import DiscoveryPath, Sv6d, assert_sv6d_within_window
from hawedit.discovery import Candidate
from hawedit.registry import resolve_role
from hawedit.visual_index import SceneWindow

__all__ = [
    "MAX_FRAMES_PER_CALL",
    "PATH_B_MODEL",
    "PathBDiscovery",
    "PathBError",
    "SceneReading",
    "SceneReadings",
    "UnreadableScene",
    "VideoUnderstanding",
    "discover_visual",
]

PATH_B_MODEL: Final = "MCG-NJU/VideoChat3-4B"
_DISCOVERY_ROLE: Final = frozenset({"visual_discovery"})

# §3: "Segmentation is mandatory: the authors report ~17.7 GB at 256 frames and ~26.7 GB at
# 512." 256 is the figure the note is written about and the one that fits a 24 GB card with
# room; 512 does not. This is a ceiling on a single call, which is what VRAM responds to.
MAX_FRAMES_PER_CALL: Final = 256


class PathBError(RuntimeError):
    """Path B refused to call the model, or refused what came back."""


@dataclass(frozen=True, slots=True)
class SceneReading:
    """One scene window as `VideoChat3-4B` read it, in §3's SV6D schema."""

    window: SceneWindow
    sv6d: Sv6d
    score: float
    model_id: str = PATH_B_MODEL

    def __post_init__(self) -> None:
        resolve_role(self.model_id, _DISCOVERY_ROLE, "the Path B video reader")
        if not math.isfinite(self.score):
            raise ValueError(
                f"reading for {self.window.window_id} has a non-finite score. NaN compares "
                f"False against everything, so this scene would sort last in every ordering "
                f"without reporting anything."
            )
        # Checked here rather than only in `discover_visual`, so a reading built by any route —
        # a future batch reader, a rehydrated JSON document — carries the same guarantee.
        assert_sv6d_within_window(self.sv6d, self.window.in_ms, self.window.out_ms)

    def to_candidate(self, rank: int) -> Candidate:
        """This reading as a §3 Stage 3 candidate. The span is the window's, never widened."""
        return Candidate(
            candidate_id=self.window.window_id,
            media_id=self.window.media_id,
            in_ms=self.window.in_ms,
            out_ms=self.window.out_ms,
            path=DiscoveryPath.VISUAL,
            rank=rank,
            score=self.score,
            sv6d=self.sv6d,
        )


@dataclass(frozen=True, slots=True)
class UnreadableScene:
    """A survivor the reader reached and could not turn into a reading.

    §3 Stage 3 fixes the SV6D schema at six dimensions and refuses output with no timeline
    evidence, so a refusal here is the guard working. What was wrong was the blast radius: one
    such window aborted the whole of Path B. This is the record that keeps "six candidates"
    from being indistinguishable from "seven, and one vanished" — the same shape D-103 gave
    Stage 1, where one unalignable region discarded a 38-minute transcript.
    """

    window_id: str
    in_ms: int
    out_ms: int
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError(
                f"unreadable scene {self.window_id} carries no reason. A window dropped for no "
                f"stated reason is a window silently dropped, which is what this type exists "
                f"to prevent."
            )
        if self.out_ms <= self.in_ms:
            raise ValueError(
                f"unreadable scene {self.window_id} spans {self.in_ms}..{self.out_ms} ms, which "
                f"has no length"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "window_id": self.window_id,
            "in_ms": self.in_ms,
            "out_ms": self.out_ms,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SceneReadings:
    """What one `read_scenes` call produced, including what it could not produce."""

    readings: tuple[SceneReading, ...]
    unreadable: tuple[UnreadableScene, ...] = ()


@dataclass(frozen=True, slots=True)
class PathBDiscovery:
    """Path B's candidates, and the survivors that yielded none."""

    candidates: tuple[Candidate, ...]
    unreadable: tuple[UnreadableScene, ...] = ()


class VideoUnderstanding(Protocol):
    """`VideoChat3-4B`'s local scene-reading interface."""

    def read_scenes(self, windows: Sequence[SceneWindow]) -> SceneReadings: ...


def discover_visual(
    windows: Sequence[SceneWindow],
    model: VideoUnderstanding,
    media_id: str,
) -> PathBDiscovery:
    """§3 Stage 3 Path B: read these scenes, return candidates ordered by the model's score.

    A window the reader refused is carried in `unreadable`, not dropped: "the model omitted
    readings" below is the guard against a *model* losing scenes, and it cannot tell that apart
    from a reading this side declined to use. Both are recall destroyed; only one is the
    model's fault, and they need different reports.

    Raises:
        PathBError: a window belongs to other media, the model did not account for every window
            in each frame-budgeted call, or no window at all could be read.
    """
    if not windows:
        # Nothing to read is not an error and is not a call. §3's union proceeds with whatever
        # either path found, and Path B finding nothing on an empty plan is not a failure.
        return PathBDiscovery(())

    foreign = sorted({w.media_id for w in windows} - {media_id})
    if foreign:
        raise PathBError(
            f"windows from media {foreign!r} were passed while discovering {media_id!r}"
        )

    batches: list[tuple[SceneWindow, ...]] = []
    current: list[SceneWindow] = []
    current_frames = 0
    for window in windows:
        if current and current_frames + window.frame_count > MAX_FRAMES_PER_CALL:
            batches.append(tuple(current))
            current = []
            current_frames = 0
        current.append(window)
        current_frames += window.frame_count
    if current:
        batches.append(tuple(current))

    all_readings: list[SceneReading] = []
    unreadable: list[UnreadableScene] = []
    for batch in batches:
        sent = {w.window_id: w for w in batch}
        produced = model.read_scenes(batch)
        readings = produced.readings
        unreadable.extend(produced.unreadable)
        seen = {scene.window_id for scene in produced.unreadable}
        foreign_failures = sorted(seen - sent.keys())
        if foreign_failures:
            raise PathBError(
                f"the model reported {foreign_failures!r} unreadable, which is not among the "
                f"{len(batch)} windows in its frame-budgeted call."
            )
        for reading in readings:
            window_id = reading.window.window_id
            if window_id not in sent:
                raise PathBError(
                    f"the model returned a reading for {window_id}, which is not among the "
                    f"{len(batch)} windows in its frame-budgeted call. A scene that was never "
                    f"shown to it has no footage behind whatever the reading claims."
                )
            if reading.window != sent[window_id]:
                raise PathBError(
                    f"the model returned {window_id} with window data that differs from the "
                    f"window it was given. A matching id does not prove it read the requested "
                    f"footage: expected {sent[window_id]!r}, got {reading.window!r}."
                )
            if window_id in seen:
                raise PathBError(
                    f"the model accounted for {window_id} twice — a second reading, or a "
                    f"reading beside a refusal for the same window. §3 Stage 2 is one embedding "
                    f"per scene and this is one reading per scene; two would give the same "
                    f"footage two chances to survive into Stage 4, and a reading beside a "
                    f"refusal is two answers with nothing choosing between them."
                )
            seen.add(window_id)

        missing = sorted(sent.keys() - seen)
        if missing:
            raise PathBError(
                f"the model omitted readings for {missing!r}. Path B requires exactly one "
                f"reading or one stated refusal for every one of the {len(batch)} windows in a "
                f"call; silently dropping scenes destroys visual recall."
            )
        all_readings.extend(readings)

    if not all_readings:
        # The only bound that needs no chosen threshold: some readings is a partial answer with
        # its gaps named, none at all is Path B having produced nothing while reporting a
        # result. D-103 drew the same line for a transcript where no region aligned.
        raise PathBError(
            f"not one of the {len(windows)} survivor(s) could be read: "
            + "; ".join(f"{scene.window_id}: {scene.reason}" for scene in unreadable)
        )

    ordered = sorted(all_readings, key=lambda r: (-r.score, r.window.in_ms, r.window.window_id))
    return PathBDiscovery(
        tuple(reading.to_candidate(rank) for rank, reading in enumerate(ordered, start=1)),
        tuple(unreadable),
    )
