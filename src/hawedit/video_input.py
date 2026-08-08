"""Putting a scene window in front a Qwen3-VL-family model, in the right place in time.

Three §7 models take video this way — `Qwen3-VL-Embedding-2B` (§3 Stage 2),
`MCG-NJU/VideoChat3-4B` (§3 Stage 3 Path B) and `MCG-NJU/TimeLens2-4B` (§3 Stage 5) — so this
is one module rather than a thing each adapter re-derives. It exists because of a measurement.

**The defect this module is about.** Hand a Qwen3-VL processor a list of pre-extracted frames
and it emits timestamp tokens into the prompt — `<0.0 seconds>`, `<2.5 seconds>` — which is how
the model is told *when* each frame group happened. With no metadata it falls back to assuming
24 fps, and §3 Stage 2's frames are **one second apart**. Measured on the real fixture: a
**4.162-second** window sampled at 1 fps reached the model stamped `0.0` and `0.1` seconds. Forty
times compressed, and nothing anywhere reports it.

Neither obvious repair works. An `fps` key inside the video content dict is accepted and
ignored: `input_ids` come out byte-identical for `fps=1`, `fps=24`, `fps=2` and no fps at all.
A `video_metadata` key inside the content dict is equally inert. What works is `video_metadata`
as a **top-level argument** to `apply_chat_template`, which is why `window_video_metadata`
exists and why it is not a detail a caller should be trusted to remember.

Why it matters differently for each model:

* Stage 2's embedding is *silently* wrong — a vector for footage the model placed in the wrong
  100 ms. `visual_index.SceneWindow` already refuses a window that quietly lowers its own frame
  rate, on the grounds that "the resulting embedding is indistinguishable from an honest one".
  This is that same failure one layer down, past that guard.
* Stage 5's TimeLens2 **returns intervals**, and M6.1 built a relevance gate that compares them
  against the anchored sentence. Intervals from a model told the window is 0.1 s long are not
  wrong by a little.

**Timestamps are window-relative, and that is deliberate.** The model is shown one window and
told how long it is, so what comes back is measured from the window's start. Absolute media time
is `window.in_ms + t`, and adding it is the caller's job — `SceneWindow` already carries the
offset. `boundary.py` takes media-absolute milliseconds, so an interval handed straight from a
model into fusion is off by the window's start. See D-049.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from hawedit.captions import find_ffmpeg
from hawedit.visual_index import SceneWindow

__all__ = [
    "TIMESTAMP_TOKEN",
    "FrameCountMismatch",
    "TimestampsOutsideWindow",
    "VideoInputError",
    "WindowFrames",
    "assert_timestamps_span_window",
    "extract_window_frames",
    "load_window_images",
    "prompt_timestamps",
    "video_content",
    "window_video_metadata",
]

# What the Qwen3-VL chat template writes into the prompt to place each temporal group in time.
TIMESTAMP_TOKEN: Final = re.compile(r"<([0-9]+(?:\.[0-9]+)?) seconds>")

# Both templates write the stamp with `f"<{t:.1f} seconds>"`, so a value read back out of the
# prompt can sit up to half of the last printed digit below the number the processor computed.
PRINTED_PRECISION_S: Final = 0.05

# The rate a Qwen3-VL processor falls back to when it is told nothing — the defect D-049 is
# about. Kept as a constant so the guard's message can name the counterfactual it is refusing.
_ASSUMED_FPS: Final = 24.0


def _last_stamp_floor(frames: WindowFrames) -> float:
    """The earliest a correct prompt can place this window's final temporal group.

    Derived rather than tuned. Both templates stamp a group with the mean of its frames' times,
    and a frame's time is its index divided by the sampling rate — so the largest stamp a
    correct processor can write is `(count - 1) / fps`, and the *smallest* is that halved: one
    group spanning every frame, stamped at its midpoint. Any finer grouping puts the last stamp
    higher, so this is a floor for every grouping at once.

    The previous bar was "half the window", which silently assumed Qwen3-VL's pairing. Measured,
    `MCG-NJU/VideoChat3-4B` merges **four** frames per group and resamples first, so six frames
    of a 1400 ms window become one group stamped 0.6 s — 42.9% of the window, and the old bar
    rejected all three of the fixture's windows. It rejected them for being correct: 0.625 s is
    exactly `(6 - 1) / (2 x 4)`, the midpoint of frames at 0.00 … 1.25 s.

    The bar still separates the failure it was written for by a wide margin, because that
    failure scales every stamp by `fps / 24`:

        window   frames  fps   floor    real stamp   at 24 fps
        s0:w0    6       4.0   0.5750   0.600        0.1000
        s1:w0    6       4.0   0.5750   0.600        0.1000
        s2:w0    5       4.0   0.4500   0.500        0.0833

    D-057.
    """
    return (frames.count - 1) / (2 * frames.window.fps) - PRINTED_PRECISION_S


class VideoInputError(RuntimeError):
    """A scene window could not be presented to a model honestly."""


class FrameCountMismatch(VideoInputError):
    """ffmpeg returned materially fewer frames than the window plans for."""


class TimestampsOutsideWindow(VideoInputError):
    """The prompt places the window's frames somewhere the window is not."""


@dataclass(frozen=True, slots=True)
class WindowFrames:
    """The frames actually extracted for one window, and how many there really are.

    `SceneWindow.frame_count` is a *plan* — `ceil(duration × fps)`. ffmpeg's `fps` filter is
    the fact, and the two differ systematically, because that filter samples at interval
    *centres*: over 4.162 s at 1 fps it emits frames at 0.5, 1.5, 2.5, 3.5 — **four**, where
    `ceil` predicts five. Measured across three window lengths on the fixture:

        4162 ms, 1 fps   plan 5   actual 4   (centres 0.5 1.5 2.5 3.5)
        1400 ms, 1 fps   plan 2   actual 1   (centre 0.5; 1.5 is past the end)
        1362 ms, 1 fps   plan 2   actual 1

    So the plan runs one high whenever the duration is not a whole number of frames. Carrying
    the measured count is the rule M3.4 established for render, where
    `RenderResult.duration_ms` was the request echoed back and the file was never opened.
    """

    window: SceneWindow
    paths: tuple[Path, ...]

    def __post_init__(self) -> None:
        if not self.paths:
            raise FrameCountMismatch(
                f"no frames were extracted for {self.window.window_id}. An empty window "
                f"embeds to nothing, and 'nothing' is not a description of that footage."
            )

    @property
    def count(self) -> int:
        """Frames that exist on disk — not `window.frame_count`, which is the plan."""
        return len(self.paths)


def extract_window_frames(
    video: Path,
    window: SceneWindow,
    dest_dir: Path,
    ffmpeg: Path | None = None,
) -> WindowFrames:
    """Sample `window`'s frames at the window's own rate, into `dest_dir`.

    The rate comes from `window.fps` rather than a constant: `SceneWindow` carries it precisely
    because 64 frames is only §3 Stage 2's published setting when they are 64 frames of one
    second each, and it refuses a window that lowered the rate to fit.

    Raises:
        VideoInputError: no ffmpeg, or ffmpeg failed.
        FrameCountMismatch: more frames than the window plans for, or more than one short. One
            frame of slack is the tail-rounding the `fps` filter really produces (measured: 5
            planned, 4 emitted, on a window whose duration is not a whole number of frames).
            Two or more short means the window runs past the end of the media, and an embedding
            of the frames that happened to exist would describe less footage than it claims.
    """
    binary = ffmpeg or find_ffmpeg()
    if binary is None:
        raise VideoInputError("no ffmpeg available — run scripts/fetch-ffmpeg.sh")

    dest_dir.mkdir(parents=True, exist_ok=True)
    pattern = dest_dir / f"{window.window_index:03d}_%04d.jpg"
    result = subprocess.run(
        [
            str(binary),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{window.in_ms / 1000:.3f}",
            "-t",
            f"{window.duration_ms / 1000:.3f}",
            "-i",
            str(video),
            "-vf",
            f"fps={window.fps}",
            "-frames:v",
            str(window.frame_count),
            "-y",
            str(pattern),
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise VideoInputError(
            f"ffmpeg failed extracting {window.window_id} "
            f"({result.returncode}): {result.stderr.decode('utf-8', 'replace')[-400:]}"
        )

    paths = tuple(sorted(dest_dir.glob(f"{window.window_index:03d}_*.jpg")))
    frames = WindowFrames(window=window, paths=paths)
    if frames.count > window.frame_count:
        raise FrameCountMismatch(
            f"{window.window_id} planned {window.frame_count} frames and ffmpeg produced "
            f"{frames.count}. More frames than the plan means the ceiling §3 Stage 2 sets is "
            f"not the ceiling being enforced."
        )
    if frames.count < window.frame_count - 1:
        raise FrameCountMismatch(
            f"{window.window_id} planned {window.frame_count} frames over "
            f"{window.duration_ms} ms and ffmpeg produced {frames.count}. One frame of tail "
            f"rounding is normal; this is {window.frame_count - frames.count}. The window "
            f"likely runs past the end of the media, and an embedding of whatever frames "
            f"existed would describe less footage than the window claims."
        )
    # A window the plan says is temporal, arriving as a single still, is the exact failure §7
    # excludes CLIP for — "frame-averaging loses temporal structure" — reached from the other
    # direction: there is no structure left to lose. It is also invisible downstream, because
    # `video_content` will wrap one frame in a video block and the embedding looks like any
    # other. Measured: the fixture's 1400 ms scenes plan 2 frames at 1 fps and yield 1.
    if window.frame_count >= 2 and frames.count < 2:
        raise FrameCountMismatch(
            f"{window.window_id} is {window.duration_ms} ms and planned {window.frame_count} "
            f"frames at {window.fps} fps, but only {frames.count} frame exists. A one-frame "
            f"video has no temporal structure at all, and its embedding is indistinguishable "
            f"from an honest window's. Raise the window's fps — `SceneWindow` permits any rate "
            f"at or above §3 Stage 2's reference {window.fps} and enforces the 64-frame ceiling "
            f"against it — or treat this scene as a still deliberately."
        )
    return frames


def window_video_metadata(frames: WindowFrames) -> dict[str, Any]:
    """The metadata a Qwen3-VL processor needs to place these frames in time.

    Pass it as a **top-level** `video_metadata=` argument to `apply_chat_template`, not inside
    the video content dict. Measured on `Qwen3-VL-Embedding-2B`, four frames of the fixture:

        no metadata                        -> <0.0 seconds> <0.1 seconds>
        fps inside the content dict        -> <0.0 seconds> <0.1 seconds>   (accepted, ignored)
        video_metadata inside the content  -> <0.0 seconds> <0.1 seconds>   (accepted, ignored)
        video_metadata= top level          -> <0.5 seconds> <2.5 seconds>   correct

    `fps` is the window's own sampling rate. `total_num_frames` is the count that exists on
    disk, never `window.frame_count` — reporting the plan would put the last frame at a time no
    frame was taken at.

    **`duration` is `total_num_frames / fps`, not the window's length**, and the difference is
    up to one frame period. `MCG-NJU/VideoChat3-4B` demands that identity in its own metadata
    type and refuses anything else — *"fps * duration must be equal to total_num_frames, but got
    5.6 != 6"* on a 1400 ms window at 4 fps. Reporting the window's 1.400 s there is not a
    rounding disagreement, it is a hard refusal, and the frames really do represent 6 slots of
    250 ms whatever the window's boundaries are.

    Nothing is given up on the other side. Measured on `Qwen3-VL-Embedding-2B`, both forms, two
    windows: identical prompt timestamps and **byte-identical** embeddings —

        4162 ms @ 1 fps, 4 frames   duration 4.1620 vs 4.0000   stamps (0.5, 2.5) both
        1400 ms @ 4 fps, 6 frames   duration 1.4000 vs 1.5000   stamps (0.2, 1.0) both

    so the field is inert for the model that was already reading it and required by the one
    added next. D-056.
    """
    window = frames.window
    return {
        "fps": window.fps,
        "duration": frames.count / window.fps,
        "total_num_frames": frames.count,
    }


def load_window_images(frames: WindowFrames) -> list[Any]:
    """`frames` as decoded RGB images, which is the only form the processor accepts.

    Measured against `Qwen3-VL-Embedding-2B`'s processor, same frames three ways:

        ["C:/…/f0001.jpg", …]         ValueError: Sampling frames from a list of images is
                                      not supported! Set `do_sample_frames=False`
                                      — and setting it does not help
        ["file://C:/…/f0001.jpg", …]  ValueError: Incorrect image source. Must be a valid URL
        [PIL.Image, …]                accepted

    Both refusals are loud, which is the one merciful thing about this path. Pillow is imported
    here rather than at module scope so the rest of this module — the metadata and the timestamp
    guard, which is what the gate checks — imports on a machine without the `gpu` extra.
    """
    from PIL import Image

    return [Image.open(path).convert("RGB") for path in frames.paths]


def video_content(images: Sequence[Any]) -> dict[str, Any]:
    """The `{"type": "video", ...}` content block for one window.

    One block with a list under `"video"`, never a list of separate image blocks: measured, a
    list of images embeds to one vector *per frame* and a video block embeds to one vector for
    the window. §7 excludes CLIP with the reason "Frame-averaging loses temporal structure —
    0.325 vs 0.75+ NDCG@10", so taking the per-frame shape and reducing it afterwards would
    rebuild, inside Stage 2, the thing §7 rejected — and the index would look identical.

    Takes the images rather than the `WindowFrames` so this stays free of Pillow; pass
    `load_window_images(frames)`.
    """
    if not images:
        raise VideoInputError("a video content block with no frames describes nothing")
    return {"type": "video", "video": list(images)}


def prompt_timestamps(prompt_text: str) -> tuple[float, ...]:
    """Every `<N seconds>` marker the chat template wrote, in order.

    This is the *artifact*: what the model is actually told about time, read back out of the
    tokenised prompt rather than inferred from the arguments that were passed.
    """
    return tuple(float(match) for match in TIMESTAMP_TOKEN.findall(prompt_text))


def assert_timestamps_span_window(prompt_text: str, frames: WindowFrames) -> tuple[float, ...]:
    """Refuse a prompt that places this window's frames outside the window.

    Checked on the decoded prompt, because every other layer accepts the wrong answer
    silently: the `fps` key is accepted and ignored, `video_metadata` in the content dict is
    accepted and ignored, and the tokenised ids are byte-identical either way. The timestamps
    are the only place the mistake becomes visible.

    Returns:
        The timestamps, once accepted, so a caller can record them as evidence.

    Raises:
        TimestampsOutsideWindow: no timestamps at all, some stamp lands outside the window, or
            the last one falls below `_last_stamp_floor` — the earliest a correct processor can
            place it, given the frames and the rate. The failing case is real and is the
            default: 0.0 and 0.1 seconds for a 4162 ms window.
    """
    stamps = prompt_timestamps(prompt_text)
    window = frames.window
    duration_s = window.duration_ms / 1000.0

    if not stamps:
        raise TimestampsOutsideWindow(
            f"the prompt for {window.window_id} carries no <N seconds> marker, so the model is "
            f"told nothing about when these frames happened."
        )
    if any(t < 0 or t > duration_s for t in stamps):
        raise TimestampsOutsideWindow(
            f"{window.window_id} spans {duration_s:.3f} s and the prompt stamps frames at "
            f"{list(stamps)} — outside the window."
        )

    if max(stamps) < _last_stamp_floor(frames):
        broken = max(stamps) * window.fps / _ASSUMED_FPS
        raise TimestampsOutsideWindow(
            f"{window.window_id} holds {frames.count} frames {window.fps} fps apart, so a "
            f"correct prompt cannot stamp the last group before "
            f"{_last_stamp_floor(frames):.3f} s — this one stamps it at {max(stamps):.3f} s. "
            f"That is what happens when video_metadata is not passed as a top-level argument: "
            f"the processor assumes {_ASSUMED_FPS:g} fps, which would put it near "
            f"{broken:.3f} s. Nothing downstream can see this."
        )
    return stamps
