"""Placing a scene window in time for a Qwen3-VL model — the check on a real defect.

Hand a Qwen3-VL processor a list of pre-extracted frames with no metadata and it stamps them
into the prompt as if they were 24 fps. Measured on the fixture: a **4162 ms** window sampled at
1 fps reached the model marked `<0.0 seconds>` and `<0.1 seconds>`. Every layer between accepts
the wrong answer without a word — an `fps` key in the content dict is ignored, `video_metadata`
in the content dict is ignored, and the tokenised ids are byte-identical either way.

So the tests here assert on the **decoded prompt**, which is the only place the mistake is
visible, and the negative control is not invented: `[0.0, 0.1]` is what the processor really
produced before the fix. A guard that passed for both that and `[0.5, 2.5]` would measure
nothing, and this file exists because three §7 models take video through this path.

The processor itself needs 4 GB of weights, so the end-to-end run is recorded in
`evidence/m5-2-video-timestamps.md`; everything here is pure and runs on any machine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.video_input import (
    FrameCountMismatch,
    TimestampsOutsideWindow,
    VideoInputError,
    WindowFrames,
    assert_timestamps_span_window,
    extract_window_frames,
    prompt_timestamps,
    video_content,
    window_video_metadata,
)
from hawedit.visual_index import SceneWindow

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")

# The fixture, as tests/test_ingest.py measures it: three 1.4 s segments, 4162 ms total.
FIXTURE_MS = 4_162


def a_window(duration_ms: int = FIXTURE_MS, fps: float = 1.0, in_ms: int = 0) -> SceneWindow:
    return SceneWindow(
        media_id="kurdish-speech-3cuts",
        scene_index=0,
        window_index=0,
        in_ms=in_ms,
        out_ms=in_ms + duration_ms,
        fps=fps,
    )


def frames_for(window: SceneWindow, count: int) -> WindowFrames:
    return WindowFrames(window=window, paths=tuple(Path(f"f{i:04d}.jpg") for i in range(count)))


# --- the metadata, built from the window and the frames that exist ------------------------


def test_metadata_carries_the_windows_own_rate() -> None:
    """The model places frames using this number; a constant would place them wrongly."""
    assert window_video_metadata(frames_for(a_window(), 4))["fps"] == 1.0


def test_duration_is_the_identity_videochat3_demands() -> None:
    """`fps x duration == total_num_frames`, exactly — the checkpoint's own validator.

    Reporting the window's 4.162 s here is not a rounding disagreement with
    `MCG-NJU/VideoChat3-4B`, it is a refusal: *"fps * duration must be equal to
    total_num_frames, but got 5.6 != 6"*. Measured free on the other side — Qwen3-VL returns
    byte-identical embeddings for both forms. D-056.
    """
    for count, fps in ((4, 1.0), (6, 4.0), (5, 4.0), (32, 2.0)):
        metadata = window_video_metadata(frames_for(a_window(fps=fps), count))
        assert metadata["fps"] * metadata["duration"] == pytest.approx(
            metadata["total_num_frames"], abs=1e-6
        )
    # And it is genuinely not the window's own length, which is what it used to be.
    assert window_video_metadata(frames_for(a_window(), 4))["duration"] == pytest.approx(4.0)


def test_metadata_reports_the_frames_that_exist_not_the_frames_planned() -> None:
    """`SceneWindow.frame_count` is `ceil(4.162) = 5`; ffmpeg emits 4. The plan is not the fact.

    Reporting 5 would put the last frame at a time no frame was taken at — M3.4's rule, where
    `RenderResult.duration_ms` was the request echoed back and the file was never opened.
    """
    window = a_window()
    assert window.frame_count == 5
    assert window_video_metadata(frames_for(window, 4))["total_num_frames"] == 4


def test_a_window_at_a_higher_rate_reports_that_rate() -> None:
    window = a_window(duration_ms=8_000, fps=4.0)
    assert window_video_metadata(frames_for(window, 32))["fps"] == 4.0


# --- the content block: one video, never a list of images ----------------------------------


def test_the_window_goes_in_as_one_video_block() -> None:
    """Measured: a list of images embeds to one vector *per frame*, a video block to one vector.

    §7 excludes CLIP because "frame-averaging loses temporal structure — 0.325 vs 0.75+
    NDCG@10", so the per-frame shape plus a mean afterwards is the thing §7 rejected, rebuilt
    inside Stage 2 where the index would look identical.
    """
    content = video_content(["frame0", "frame1", "frame2", "frame3"])
    assert content["type"] == "video"
    assert isinstance(content["video"], list) and len(content["video"]) == 4


def test_a_content_block_with_no_frames_is_refused() -> None:
    with pytest.raises(VideoInputError, match="describes nothing"):
        video_content([])


# --- the artifact check, and the negative control that makes it mean something -------------


def test_the_real_broken_timestamps_are_refused() -> None:
    """`[0.0, 0.1]` is not invented — it is what the processor produced for this window.

    This is the negative control. Without it every assertion below would also pass on the
    broken output, and the guard would measure nothing.
    """
    frames = frames_for(a_window(), 4)
    broken = "<|vision_start|><0.0 seconds><|video_pad|><0.1 seconds><|video_pad|>"
    with pytest.raises(TimestampsOutsideWindow, match="assumes 24 fps"):
        assert_timestamps_span_window(broken, frames)


def test_the_real_videochat3_timestamps_are_accepted() -> None:
    """One stamp at 0.6 s for six frames of a 1400 ms window — and the old bar rejected it.

    `MCG-NJU/VideoChat3-4B` merges **four** frames per temporal group and resamples first, so
    six frames become one group stamped at their midpoint: `(0 + 5/4) / 2 = 0.625`, printed
    `0.6`. The previous rule wanted half the window, 0.7, and rejected all three of the
    fixture's windows for being correct. D-057.
    """
    frames = frames_for(a_window(duration_ms=1_400, fps=4.0), 6)
    assert assert_timestamps_span_window("<0.6 seconds>", frames) == (0.6,)


def test_the_24_fps_counterfactual_of_that_same_window_is_refused() -> None:
    """The negative control for the bar above, at the same frame count and rate.

    The defect scales every stamp by `fps / 24`, so the same group lands at 0.1 s. A floor that
    accepted 0.6 and 0.1 alike would have replaced a mis-calibrated check with no check.
    """
    frames = frames_for(a_window(duration_ms=1_400, fps=4.0), 6)
    with pytest.raises(TimestampsOutsideWindow, match="cannot stamp the last group"):
        assert_timestamps_span_window("<0.1 seconds>", frames)


def test_the_real_correct_timestamps_are_accepted() -> None:
    """`[0.5, 2.5]` is what the processor produces once video_metadata is passed top-level.

    Two stamps for four frames because Qwen3-VL groups frames in pairs, and each stamp sits at
    its group's midpoint — 0.5 covers t=0,1 and 2.5 covers t=2,3.
    """
    frames = frames_for(a_window(), 4)
    good = "<|vision_start|><0.5 seconds><|video_pad|><2.5 seconds><|video_pad|>"
    assert assert_timestamps_span_window(good, frames) == (0.5, 2.5)


def test_a_prompt_with_no_timestamp_at_all_is_refused() -> None:
    """A prompt carrying no marker tells the model nothing about when the frames happened."""
    with pytest.raises(TimestampsOutsideWindow, match="no <N seconds> marker"):
        assert_timestamps_span_window("<|vision_start|><|video_pad|>", frames_for(a_window(), 4))


def test_a_timestamp_past_the_end_of_the_window_is_refused() -> None:
    """The other direction. A stamp outside the window is as wrong as one compressed inside it."""
    with pytest.raises(TimestampsOutsideWindow, match="outside the window"):
        assert_timestamps_span_window("<9999.0 seconds>", frames_for(a_window(), 4))


def test_timestamps_are_parsed_in_order() -> None:
    assert prompt_timestamps("<2.5 seconds> then <0.5 seconds>") == (2.5, 0.5)


def test_integer_and_fractional_markers_both_parse() -> None:
    """The template writes `0.0` here and could write `3`; a parser that took only one is a
    guard that stops firing on the day the template changes."""
    assert prompt_timestamps("<3 seconds><0.25 seconds>") == (3.0, 0.25)


# --- frames on disk ------------------------------------------------------------------------


def test_a_window_with_no_frames_is_refused() -> None:
    with pytest.raises(FrameCountMismatch, match="no frames"):
        WindowFrames(window=a_window(), paths=())


@needs_ffmpeg
def test_extraction_samples_the_real_fixture_at_the_windows_own_rate(tmp_path: Path) -> None:
    """Runs the binary. 5 planned, and what lands on disk is what `count` reports."""
    window = a_window()
    frames = extract_window_frames(FIXTURE, window, tmp_path)
    assert frames.count in (window.frame_count - 1, window.frame_count), frames.count
    assert all(path.exists() and path.stat().st_size > 0 for path in frames.paths)
    assert window_video_metadata(frames)["total_num_frames"] == frames.count


@needs_ffmpeg
def test_a_short_window_that_yields_one_frame_at_1_fps_is_refused(tmp_path: Path) -> None:
    """The fixture's own 1400 ms scenes. Plan 2 frames at 1 fps, ffmpeg emits 1.

    A one-frame "video" has no temporal structure to lose, which is §7's stated reason for
    excluding CLIP arrived at from the other side — and `video_content` would wrap it in a
    video block whose embedding looks like any other window's. Found by measuring
    `plan_scene_windows` output on the real fixture, not by reasoning about it.
    """
    short = a_window(duration_ms=1_400, fps=1.0)
    assert short.frame_count == 2
    with pytest.raises(FrameCountMismatch, match="no temporal structure"):
        extract_window_frames(FIXTURE, short, tmp_path)


@needs_ffmpeg
def test_the_same_short_window_at_a_higher_rate_is_accepted(tmp_path: Path) -> None:
    """The positive control on the refusal above, and the remedy it names.

    Without this, the guard could be satisfied by refusing every short window — which would
    also refuse the fix. `SceneWindow` permits any rate at or above the reference and enforces
    the 64-frame ceiling against it, so 4 fps over 1400 ms is legal and has real frames.
    """
    faster = a_window(duration_ms=1_400, fps=4.0)
    frames = extract_window_frames(FIXTURE, faster, tmp_path)
    assert frames.count >= 2, frames.count
    assert window_video_metadata(frames)["fps"] == 4.0


@needs_ffmpeg
def test_a_window_running_past_the_end_of_the_media_is_refused(tmp_path: Path) -> None:
    """Two frames short is not tail rounding — it is a window the media does not cover.

    Embedding whatever frames happened to exist would describe less footage than the window
    claims, which is §8.3's shipped-clip lesson applied to Stage 2's input.
    """
    beyond = a_window(duration_ms=20_000, in_ms=0)
    with pytest.raises(FrameCountMismatch, match="past the end of the media"):
        extract_window_frames(FIXTURE, beyond, tmp_path)
