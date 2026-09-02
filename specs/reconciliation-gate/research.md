# Research — Reconciliation Gate in Delivery (T1.2)

## 1. Objective and Problem Statement

Task **T1.2** in `specs/pro-grade-program/tasks.md` introduces the **Reconciliation Gate** (Proof Level C):
> Before the delivery publish, run independent measurement (`hawedit.measure`) on the staged private media artifacts and require that every claim made in the contract matches what the delivered pixels and audio actually contain. If any claim diverges, delivery MUST halt with `DeliveryRefused(reason, expected, measured)` and roll back private staging.

This eliminates rows 1, 2, 3, 5, 8, and 9 in the claims-without-measurement register (`specs/pro-grade-program/research.md` §5):
1. `captions_burned_in: true` was an unconditional constant.
2. `RenderResult.width/height` were constants (1080×1920) never checked against `ffprobe`.
3. `crop_target: face_tracked` was stamped from a single focus point without verifying that a face stayed in frame.
4. `silence_removed_ms` was an unchecked arithmetic number.
5. Planned punch-in cuts were assumed to exist in the video without checking visual scene cuts (`scdet`).
6. Audio loudness (−14 LUFS / −1 dBTP) was trusted from the ffmpeg filter string without EBU R128 verification on the output file.

## 2. Existing Code Mapping

### 2.1 Delivery Boundary (`src/hawedit/delivery.py`)
- Defines `DeliveryError`, `build_srt`, `build_edl`, `parse_srt_times`, etc.
- Currently does NOT define `DeliveryRefused` or any reconciliation functions.
- `DeliveryRefused` must inherit from `DeliveryError` and capture:
  ```python
  class DeliveryRefused(DeliveryError):
      def __init__(self, reason: str, expected: Any, measured: Any) -> None:
          super().__init__(f"{reason}: expected {expected!r}, measured {measured!r}")
          self.reason = reason
          self.expected = expected
          self.measured = measured
  ```

### 2.2 Atomic Publication (`src/hawedit/artifact_bundle.py`)
- Defines `ArtifactBundle` which publishes files atomically using `rename_directory_noreplace`.
- `_SUFFIXES: Final = ("ass", "mp4", "srt", "edl", "json")` defines the 5-file bundle.
- T1.2 specifies: "The measured file ships as the sixth delivery file."
- Suffix set widens to: `_SUFFIXES: Final = ("ass", "mp4", "srt", "edl", "json", "measured.json")`.
- When `staged_path("measured.json")` is queried, it maps to `<bundle_id>.measured.json`.
- `ArtifactBundle.publish()` validates that all 6 files exist, are regular non-empty files, and fsyncs them before atomic publication.

### 2.3 Pipeline Delivery Stage (`src/hawedit/pipeline.py`)
- In `pipeline.py:2497-2525`:
  - `editing_json`, `srt`, and `edl` are staged into `bundle`.
  - Currently calls `bundle.publish()` directly without verification.
  - T1.2 inserts:
    1. Independent measurement:
       ```python
       measurement = measure_clip(
           video_path=render_path,
           ass_path=ass_path,
           ffmpeg=ffmpeg,
       )
       bundle.write_text("measured.json", measurement.to_json())
       ```
    2. Reconciliation gate verification:
       ```python
       reconcile_delivery(
           clip=clip,
           measurement=measurement,
           planned_punch_ins=punch_ins,
           source_shot_cuts_ms=ingested.shot_cuts_ms,
           fps=rendered.fps,
       )
       ```
    3. `bundle.publish()` only proceeds if reconciliation succeeds. If `DeliveryRefused` is raised, private staging is safely discarded and `run.delivery` is recorded as `StageSkipped`.

### 2.4 Seven Non-Negotiable Reconciliation Clauses
1. **Duration**: `abs(clip.durations[0]*1000 - measurement.video.duration_ms) <= frame_ms + 1` (or `clip.duration_ms`).
2. **Resolution & Geometry**: `measurement.video.width == 1080 and measurement.video.height == 1920`.
3. **Loudness**: `abs(measurement.audio.integrated_lufs - (-14.0)) <= 0.5` and `measurement.audio.true_peak_db <= -0.9` (matching measured ceiling).
4. **Silence Duration**: `abs(clip.silence_removed_ms - (span_ms - measurement.audio.duration_ms)) <= frame_ms + 1`.
5. **Punch-Ins & Cuts**:
   - Every planned punch-in `at_ms` must have a measured `scdet` cut within `±1 frame`.
   - No unplanned `scdet` cut is `> SHOT_CUT_GUARD_MS` (1,500 ms) away from a source camera cut.
6. **Captions Burned-In**:
   - If contract claims `captions_burned_in == True`, require `measurement.captions.ink_energy_detected_share >= 0.95`.
   - If `captions_burned_in == False`, require `measurement.captions.ink_energy_detected_share == 0.0`.
7. **Face Tracking**:
   - If contract claims `crop_target == "face_tracked"`, require `measurement.faces.face_detected_share >= 0.90`.
   - If `crop_target != "face_tracked"`, this clause does not bind.

## 3. Threat Model & Failure Modes
- **Threat 1: Faking via mock measurement.** The reconciliation function must accept real `ClipMeasurement` data structures; `pipeline.py` invokes `hawedit.measure.measure_clip` on the actual on-disk MP4 file.
- **Threat 2: Partial delivery leakage.** `bundle.publish()` must happen strictly *after* `reconcile_delivery()` passes. Any `DeliveryRefused` exception triggers `bundle.discard()` before `publish()` can be called.
- **Threat 3: Tolerances too loose or too tight.** Frame-level timing at 25 fps has 40 ms duration; audio and container multiplexing can introduce ±1 frame delta. Explicit `±1 frame` tolerance avoids false refusals on rounding while catching genuine drift.
- **Threat 4: Backwards compatibility with test bundles.** Tests in `test_artifact_bundle.py` that test bundle staging must stage all 6 files when testing full bundles.
