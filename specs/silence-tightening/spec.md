# Specification: Silence Tightening Wired End-to-End (Task T3.3, ADR D-266)

## 1. Acceptance Criteria (EARS Format)

### AC-1: Parameterized Activation
- **WHEN** the pipeline is invoked without `--silence-threshold-ms` (or with `silence_threshold_ms=0`), **THE** system **SHALL** leave media, captions, and timeline unmodified, publishing clips with `silence_removed_ms=0` (zero unprompted change).
- **WHEN** the pipeline is invoked with `--silence-threshold-ms <ms>` with $\text{ms} > 0$, **THE** system **SHALL** detect all word-internal pauses $> \text{threshold\_ms}$ and tighten them to `target_gap_ms` (default 150 ms).

### AC-2: Timeline & Media Splicing
- **WHEN** silence tightening excises paused intervals, **THE** system **SHALL** splice audio and video using FFmpeg trim/concat stream filters, resulting in a rendered MP4 whose physical audio duration matches `span_ms - silence_removed_ms` within $\pm 1$ frame tolerance.

### AC-3: Downstream Event Synchronization
- **WHEN** media is tightened, **THE** system **SHALL** shift all subsequent word timestamps, sentence timings, ASS subtitle events, camera punch-in cuts, and face tracking coordinates earlier by the cumulative removed duration at each event's source timestamp.

### AC-4: Delivery Reconciliation Compliance
- **WHEN** a tightened clip is delivered, **THE** delivery reconciliation gate **SHALL** verify:
  1. Clause 1: `abs(measured_duration_ms - clip.output.durations[0] * 1000) <= tolerance_ms`
  2. Clause 4: `abs(clip.output.silence_removed_ms - (span_ms - measured_audio_dur)) <= tolerance_ms`
  3. Clause 5: Every planned punch-in cut matches a visual scene cut in the tightened MP4.
  4. Clause 6: Caption band ink energy covers $\ge 95\%$ of caption events on the tightened timeline.

### AC-5: Invariant Preservation
- **WHEN** silence tightening is applied, **THE** system **SHALL** strictly preserve:
  - Kurdish invariant #1: Source media and transcripts are never modified in place.
  - Kurdish invariant #2: In-points and out-points bound complete sentences.
  - Kurdish invariant #4: Captions are within clip bounds and never out of sync.
