# Specification: Eased Push-Ins (Task T2.6)

## 1. Overview
This specification defines the eased push-in framing engine for HawEdit (`specs/pro-grade-program/tasks.md` Task T2.6). Eased push-ins replace mechanical square-wave zoom alternation with continuous, smoothly eased digital creep zooms (1.00x -> 1.08x) over the course of each speech shot, while preserving crisp hard cuts on source angle changes and natural speech pauses.

## 2. Requirements & Acceptance Criteria (EARS)

### Criterion 1: Shot Interval Partitioning
- **WHEN** `shot_spans(boundaries_ms, clip_duration_ms, source_cuts_ms)` is called with word pause boundaries and source cuts,
- **THE** system SHALL partition the clip `[0, clip_duration_ms]` into contiguous, non-overlapping `[start_ms, end_ms]` intervals where:
  1. The first shot opens at `0` ms and the final shot ends at `clip_duration_ms`.
  2. Every boundary separating two shots is separated from its predecessor by at least `min_shot_ms` (default 3,000 ms).
  3. Pause boundaries within `guard_ms` (1,500 ms) of any source cut are omitted.
  4. Contiguity is preserved: `shot[i].end_ms == shot[i+1].start_ms`.

### Criterion 2: Continuous Eased Zoom Keyframing
- **WHEN** `eased_push_schedule(shot_spans, push_zoom=1.08, step_ms=100)` is invoked,
- **THE** system SHALL generate a tuple of `(at_ms, factor)` keyframes such that:
  1. Each shot begins at `factor = 1.00` (or `base_zoom`).
  2. Over the shot duration, `factor` monotonically increases towards `push_zoom` according to the cubic smoothstep easing function $S(p) = 3p^2 - 2p^3$.
  3. The final frame of each shot reaches `push_zoom` (within floating point precision).
  4. Keyframes are spaced by at most `step_ms` (default 100 ms).

### Criterion 3: Hard Cut Preservation
- **WHEN** a shot transitions to the subsequent shot at `shot_end_ms`,
- **THE** system SHALL reset `factor` instantaneously back to `1.00` at the start of the new shot, producing a clean hard cut rather than a reverse easing.

### Criterion 4: Crop Filter and Render Integration
- **WHEN** `render_clip` is called with an eased push-in schedule,
- **THE** system SHALL pass the keyframes directly into `crop_filter` which converts them into FFmpeg `sendcmd` instructions, rendering a valid 1080x1920 MP4 video without encoder or muxing errors.
