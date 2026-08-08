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

import math
from pathlib import Path

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.video_input import (
    FrameCountMismatch,
    TimestampsOutsideWindow,
    VideoInputError,
    WindowFrames,
    assert_frames_reached_model,
    assert_timestamps_span_window,
    extract_window_frames,
    frames_seen_by_model,
    prompt_timestamps,
    video_content,
    window_batch,
    window_video_metadata,
)
from hawedit.visual_index import (
    DECLARED_SAMPLING_FPS,
    REFERENCE_FPS,
    TEMPORAL_PATCH_FRAMES,
    SceneWindow,
    plan_scene_windows,
)

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


def an_unplannable_window(duration_ms: int, fps: float, in_ms: int = 0) -> SceneWindow:
    """A window at a rate `SceneWindow` now refuses (D-063), constructed anyway.

    `assert_frames_reached_model` reads the frame count back off the batch precisely because the
    checkpoints' declared preprocessing is *theirs*, not ours: if a future checkpoint ships a
    different `fps` or `min_frames`, the planner's bound is stale and the guard is the only thing
    left. So the guard has to stay tested at rates the planner can no longer produce, with the
    numbers that were actually measured (D-060) rather than re-derived at a legal rate — and at
    every legal rate nothing is dropped, which is the whole point of the bound.

    The bypass is here, once, and nowhere in `src/`.
    """
    window = object.__new__(SceneWindow)
    for field, value in (
        ("media_id", "kurdish-speech-3cuts"),
        ("scene_index", 0),
        ("window_index", 0),
        ("in_ms", in_ms),
        ("out_ms", in_ms + duration_ms),
        ("fps", fps),
    ):
        object.__setattr__(window, field, value)
    return window


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
        metadata = window_video_metadata(
            frames_for(an_unplannable_window(4_162, fps) if fps > 2.0 else a_window(fps=fps), count)
        )
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
    window = an_unplannable_window(8_000, 4.0)
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
    frames = frames_for(an_unplannable_window(1_400, 4.0), 6)
    assert assert_timestamps_span_window("<0.6 seconds>", frames) == (0.6,)


def test_the_24_fps_counterfactual_of_that_same_window_is_refused() -> None:
    """The negative control for the bar above, at the same frame count and rate.

    The defect scales every stamp by `fps / 24`, so the same group lands at 0.1 s. A floor that
    accepted 0.6 and 0.1 alike would have replaced a mis-calibrated check with no check.
    """
    frames = frames_for(an_unplannable_window(1_400, 4.0), 6)
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
    faster = an_unplannable_window(1_400, 4.0)
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


# --- the frames the model actually reads, which is a different number ----------------------
#
# Every §7 visual checkpoint ships `do_sample_frames: true` with its own `fps: 2` and
# `min_frames: 4`, so the processor re-samples whatever it is handed and pads to a whole number
# of temporal patches. Measured on `Qwen3-VL-Embedding-2B` by reading `video_grid_thw` back:
# M5.2's shipped 4 fps index handed over 6 frames and the model saw 4. Every number below is
# from that table (`evidence/m5-2-frames-reaching-the-model.md`), not invented.


class _Grid:
    """`video_grid_thw`: one row per video, `[grid_t, grid_h, grid_w]`."""

    def __init__(self, grid_t: int) -> None:
        self.rows = [[grid_t, 22, 40]]

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> list[int]:
        return self.rows[index]


class _VideoProcessor:
    """The three fields the guard reads, at `Qwen3-VL-Embedding-2B`'s declared values."""

    fps = 2
    min_frames = 4
    temporal_patch_size = 2


class _Processor:
    def __init__(self, seen: int | None, prompt: str = "<0.5 seconds><2.5 seconds>") -> None:
        self.seen = seen
        self.prompt = prompt
        self.calls: list[dict[str, object]] = []
        self.video_processor = _VideoProcessor()

    def apply_chat_template(self, messages: object, **kwargs: object) -> dict[str, object]:
        self.calls.append({"messages": messages, **kwargs})
        batch: dict[str, object] = {"input_ids": [[1, 2, 3]]}
        if self.seen is not None:
            batch["video_grid_thw"] = _Grid(self.seen // self.video_processor.temporal_patch_size)
        return batch

    def decode(self, ids: object, **kwargs: object) -> str:
        return self.prompt


def test_the_frame_count_is_read_off_the_grid_not_off_the_request() -> None:
    """`WindowFrames.count` is what we handed over; `video_grid_thw` is what arrived."""
    processor = _Processor(seen=4)
    batch = processor.apply_chat_template([])
    assert frames_seen_by_model(processor, batch) == 4


def test_a_batch_with_no_video_reports_nothing_rather_than_zero() -> None:
    """`embed_text` has no frames. Zero would be a measurement; `None` is the absence of one."""
    processor = _Processor(seen=None)
    assert frames_seen_by_model(processor, processor.apply_chat_template([])) is None


def test_m5_2s_own_index_window_is_refused_because_two_frames_never_arrived() -> None:
    """The defect, at the numbers it was measured at: 6 extracted at 4 fps, 4 seen."""
    frames = frames_for(an_unplannable_window(1_400, 4.0), 6)
    processor = _Processor(seen=4)
    with pytest.raises(VideoInputError, match="the processor dropped 2"):
        assert_frames_reached_model(processor, processor.apply_chat_template([]), frames)


def test_a_full_window_above_the_declared_rate_loses_half_of_itself() -> None:
    """64 frames at 4 fps is exactly §3 Stage 2's published ceiling, and the model sees 32."""
    frames = frames_for(an_unplannable_window(16_000, 4.0), 64)
    processor = _Processor(seen=32)
    with pytest.raises(VideoInputError, match="the processor dropped 32"):
        assert_frames_reached_model(processor, processor.apply_chat_template([]), frames)


def test_an_odd_frame_count_gains_a_frame_that_was_never_filmed() -> None:
    """The second rule, and the other direction: 3 extracted, 4 seen, the last one repeated."""
    frames = frames_for(a_window(duration_ms=1_400, fps=2.0), 3)
    processor = _Processor(seen=4)
    with pytest.raises(VideoInputError, match="duplicated the last frame of 1"):
        assert_frames_reached_model(processor, processor.apply_chat_template([]), frames)


def test_a_window_at_the_declared_rate_is_accepted() -> None:
    """The positive control. A guard that refused every batch would pass all three tests above.

    64 frames at 1 fps: measured SAME — the sampler asks for 128 and caps at what exists.
    """
    frames = frames_for(a_window(duration_ms=64_000, fps=1.0), 64)
    processor = _Processor(seen=64)
    assert assert_frames_reached_model(processor, processor.apply_chat_template([]), frames) == 64


def test_the_refusal_names_both_branches_of_the_remedy() -> None:
    """A refusal naming a remedy that does not work gets worked around rather than fixed.

    The first draft of this message said "extract an even count at or below 2 fps". For a
    1400 ms scene that is unachievable — 2 fps yields 3 frames, which is odd and gets padded,
    and 1 fps yields 1, which `extract_window_frames` already refuses. The condition really has
    two branches, because `min_frames` dominates at short durations: 4 frames at 3 fps is clean.
    """
    frames = frames_for(an_unplannable_window(1_400, 4.0), 6)
    processor = _Processor(seen=4)
    with pytest.raises(VideoInputError, match="at or below 2 fps or the count at most 4"):
        assert_frames_reached_model(processor, processor.apply_chat_template([]), frames)


def test_four_frames_above_the_declared_rate_is_accepted() -> None:
    """The other branch, and the rate M5.2's index was rebuilt at: 4 frames at 3 fps.

    `max(min_frames=4, 2 x 4/3) = 4`, capped at 4, already patch-aligned — so all four arrive.
    A guard that only allowed rates at or below 2 fps would refuse this and leave a 1400 ms
    scene with no legal rate at all.
    """
    frames = frames_for(an_unplannable_window(1_400, 3.0), 4)
    processor = _Processor(seen=4)
    assert assert_frames_reached_model(processor, processor.apply_chat_template([]), frames) == 4


# --- one call, both guards ------------------------------------------------------------------


def test_window_batch_passes_video_metadata_at_the_top_level() -> None:
    """D-049, now in the one place all three adapters go through."""
    frames = frames_for(a_window(), 4)
    processor = _Processor(seen=4)
    window_batch(processor, [], frames, add_generation_prompt=False)
    metadata = processor.calls[0]["video_metadata"][0]  # type: ignore[index]
    assert metadata["fps"] == 1.0
    assert metadata["total_num_frames"] == 4


def test_window_batch_refuses_a_prompt_that_compresses_the_window() -> None:
    frames = frames_for(a_window(), 4)
    processor = _Processor(seen=4, prompt="<0.0 seconds><0.1 seconds>")
    with pytest.raises(TimestampsOutsideWindow):
        window_batch(processor, [], frames, add_generation_prompt=False)


def test_window_batch_refuses_frames_that_did_not_arrive() -> None:
    """Both guards, one function — so an adapter cannot be written with only one of them."""
    frames = frames_for(an_unplannable_window(1_400, 4.0), 6)
    processor = _Processor(seen=4, prompt="<0.2 seconds><1.0 seconds>")
    with pytest.raises(VideoInputError, match="dropped 2"):
        window_batch(processor, [], frames, add_generation_prompt=True)


def test_window_batch_returns_the_batch_when_both_guards_pass() -> None:
    frames = frames_for(a_window(), 4)
    processor = _Processor(seen=4)
    batch = window_batch(processor, [], frames, add_generation_prompt=True)
    assert "input_ids" in batch
    assert processor.calls[0]["add_generation_prompt"] is True


# --- the planner and the guard now agree, swept rather than spot-checked -------------------
#
# D-060 added `assert_frames_reached_model` and left the planner free to emit windows it
# refuses: at the rate the CLI forced, a 30 s source planned two 45-frame windows and the model
# read 30 of each. D-063 bounds the rate at the checkpoints' declared 2 fps and trims an odd
# emitted count to even, so every window a planner can produce is delivered whole.


def _model_reads(count: int, fps: float, declared: float = 2.0, minimum: int = 4) -> int:
    """The processor's own arithmetic, from the measured table in `assert_frames_reached_model`.

    Asks for `max(min_frames, declared_fps x duration)`, caps at what exists, pads up to a whole
    temporal patch. Reproduced here so the sweep can assert without 4 GB of weights; the real
    numbers it was derived from are pinned in the tests above.
    """
    wanted = max(minimum, round(declared * count / fps))
    taken = min(wanted, count)
    return taken + (taken % TEMPORAL_PATCH_FRAMES)


def test_every_plannable_window_is_delivered_to_the_model_whole() -> None:
    """The sweep. Every legal rate, a spread of durations, real `plan_scene_windows` output."""
    checked = 0
    for fps in (REFERENCE_FPS, 1.5, DECLARED_SAMPLING_FPS):
        for duration_ms in (2_000, 4_162, 7_001, 15_500, 31_000, 64_000, 121_000, 300_000):
            for window in plan_scene_windows(
                "m", duration_ms=duration_ms, shot_cuts_ms=(), fps=fps
            ):
                # What ffmpeg really emits: interval centres, so one short of the plan whenever
                # the duration is not a whole number of frames — then trimmed to even.
                emitted = math.floor(window.duration_ms * window.fps / 1000)
                if emitted < 2:
                    continue
                emitted -= emitted % TEMPORAL_PATCH_FRAMES
                assert _model_reads(emitted, window.fps) == emitted, (
                    f"{window.window_id} {window.duration_ms} ms @ {window.fps} fps: "
                    f"{emitted} frames extracted, {_model_reads(emitted, window.fps)} read"
                )
                checked += 1
    assert checked > 40, f"the sweep only covered {checked} windows"


def test_the_rate_the_cli_used_to_force_is_refused_at_planning_time() -> None:
    """The negative control, at the number that was actually shipping.

    3.0 fps planned two 45-frame windows over 30 s and the model read 30 of each — a third of
    every window discarded after ffmpeg had written it. The refusal now arrives before any frame
    is extracted, and it names what the model would have read.
    """
    with pytest.raises(ValueError, match="above the 2.0 fps"):
        plan_scene_windows("m", duration_ms=30_000, shot_cuts_ms=(), fps=3.0)


def test_the_sweep_would_fail_at_a_rate_the_bound_now_excludes() -> None:
    """And the control on the control: the arithmetic really does drop frames above 2 fps.

    Without this, `test_every_plannable_window_is_delivered_to_the_model_whole` would pass for a
    `_model_reads` that returned its input.
    """
    assert _model_reads(44, 3.0) == 30
    assert _model_reads(64, 4.0) == 32
    assert _model_reads(64, 1.0) == 64


@needs_ffmpeg
def test_an_odd_emitted_count_is_trimmed_rather_than_padded_by_the_processor(
    tmp_path: Path,
) -> None:
    """Real ffmpeg, real files on disk. 1400 ms at 2 fps emits three frames.

    Three is odd, and the processor pads an odd count by **repeating the last frame** (D-060) —
    so the model would see a frame that was never filmed, at the moment the window ends, biasing
    a temporal reading toward its own tail. Trimming to two costs one sampling interval of tail
    and leaves every frame the model sees a frame that existed. D-063.

    Asserted on the artifact: the JPEGs `extract_window_frames` actually kept.
    """
    window = a_window(duration_ms=1_400, fps=DECLARED_SAMPLING_FPS)
    frames = extract_window_frames(FIXTURE, window, tmp_path)
    assert frames.count == 2, f"expected the odd third frame trimmed, got {frames.count}"
    assert frames.count % TEMPORAL_PATCH_FRAMES == 0
    assert all(path.exists() for path in frames.paths)
    # The trimmed frame is still on disk — trimming is a decision about what to hand over, not a
    # deletion, so nothing about the extraction has to be re-run to change it.
    assert len(sorted(tmp_path.glob("000_*.jpg"))) == 3
