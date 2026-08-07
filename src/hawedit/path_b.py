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
numbers it is mandatory because of. Handing 320 frames to a 24 GB card is not a wrong answer,
it is an out-of-memory kill part-way through a batch — so the budget is checked before the
model is called, not after it dies.

**A timestamp is not evidence unless it points at the scene.** `Sv6d` has always required each
label to cite a time, and could only require that, since the type does not know which scene it
belongs to. `speaker at 9999s` on a twelve-second scene satisfies it: two and three-quarter
hours away, regex matched, claim anchored to a moment the model was never shown.
`assert_sv6d_within_window` closes it and every `SceneReading` runs through it.

What this module does *not* do is rank against Path A, dedupe across paths, or widen a span.
`discovery.py` owns the union and §3 Stage 5 owns boundaries; a candidate here spans exactly
the window it was read from.

The model is `BLOCKED.md` #2 (GPU) and #6 (weights). This is the type it will return.
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
    "PathBError",
    "SceneReading",
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


class VideoUnderstanding(Protocol):
    """`VideoChat3-4B`'s interface (`BLOCKED.md` #2, #6)."""

    def read_scenes(self, windows: Sequence[SceneWindow]) -> tuple[SceneReading, ...]: ...


def discover_visual(
    windows: Sequence[SceneWindow],
    model: VideoUnderstanding,
    media_id: str,
) -> tuple[Candidate, ...]:
    """§3 Stage 3 Path B: read these scenes, return candidates ordered by the model's score.

    Raises:
        PathBError: a window belongs to other media, the call would exceed the frame budget,
            or the model returned a scene it was not given / returned one twice.
    """
    if not windows:
        # Nothing to read is not an error and is not a call. §3's union proceeds with whatever
        # either path found, and Path B finding nothing on an empty plan is not a failure.
        return ()

    foreign = sorted({w.media_id for w in windows} - {media_id})
    if foreign:
        raise PathBError(
            f"windows from media {foreign!r} were passed while discovering {media_id!r}"
        )

    frames = sum(w.frame_count for w in windows)
    if frames > MAX_FRAMES_PER_CALL:
        raise PathBError(
            f"{len(windows)} windows are {frames} frames, past the {MAX_FRAMES_PER_CALL}-frame "
            f"budget for one call. §3: 'Segmentation is mandatory: the authors report ~17.7 GB "
            f"at 256 frames and ~26.7 GB at 512.' Past the budget this does not answer badly, "
            f"it is killed mid-batch — so the call is refused before it is made."
        )

    sent = {w.window_id: w for w in windows}
    readings = model.read_scenes(tuple(windows))

    seen: set[str] = set()
    for reading in readings:
        window_id = reading.window.window_id
        if window_id not in sent:
            raise PathBError(
                f"the model returned a reading for {window_id}, which is not among the "
                f"{len(windows)} windows it was given. A scene that was never shown to it has "
                f"no footage behind whatever the reading claims."
            )
        if window_id in seen:
            raise PathBError(
                f"the model returned {window_id} twice. §3 Stage 2 is one embedding per scene "
                f"and this is one reading per scene; two would give the same footage two "
                f"chances to survive into Stage 4."
            )
        seen.add(window_id)

    ordered = sorted(readings, key=lambda r: (-r.score, r.window.in_ms, r.window.window_id))
    return tuple(reading.to_candidate(rank) for rank, reading in enumerate(ordered, start=1))
