# Plan — Independent Measurement Module (`hawedit.measure`)

## Status
Approved-by: Hawa

## Goal
Implement `src/hawedit/measure.py` as an independent, subprocess-callable measurement tool that probes delivered MP4 video and subtitle artifacts to produce `<clip>.measured.json`, establishing ground-truth Level B verification with zero reliance on render plans or pipeline internal state.

## Proposed Changes

### Task 1: Data Structures & Container Probing (`src/hawedit/measure.py`)
1. Define immutable data models:
   - `ClipMeasurement`, `VideoMeasurement`, `AudioMeasurement`, `SilenceInterval`, `FaceTrackMeasurement`, `CaptionMeasurement`, `MeasureError`.
2. Implement `probe_container(video_path: Path, ffprobe: Path) -> VideoMeasurement`:
   - Runs `ffprobe -show_entries ... -of json`.
   - Extracts width, height, exact fractional FPS, duration, frame count, bitrate, codec, pixel format, colour metadata, and calculates media file SHA-256 and byte size.

### Task 2: Audio Dynamics & Scene Transitions (`src/hawedit/measure.py`)
1. Implement `probe_audio_dynamics(video_path: Path, ffmpeg: Path) -> AudioMeasurement`:
   - Runs ffmpeg `ebur128` filter to extract Integrated Loudness (`I`), True Peak (`TP`), and Loudness Range (`LRA`).
   - Runs ffmpeg `silencedetect` to extract pause intervals (`start_ms`, `end_ms`, `duration_ms`), total silence, and silence percentage.
2. Implement `probe_scene_cuts(video_path: Path, ffmpeg: Path) -> list[int]`:
   - Runs ffmpeg `select='gt(scene,0.3)',showinfo` to detect visual cuts.

### Task 3: Face Framing & Caption Ink Energy (`src/hawedit/measure.py`)
1. Implement `probe_face_tracking(video_path: Path, sample_fps: float = 5.0) -> FaceTrackMeasurement`:
   - Samples frames using OpenCV and executes Haar cascade detection.
   - Computes face detection rate, median face height share, and median vertical center share.
2. Implement `probe_caption_ink(video_path: Path, ass_path: Path | None = None) -> CaptionMeasurement`:
   - Reads subtitle cue timings and inspects the designated caption band for high-frequency edge energy and luminance contrast ratio against background.

### Task 4: Output Serialization & CLI Interface (`src/hawedit/measure.py`)
1. Implement `measure_clip(video_path: Path, ass_path: Path | None = None, mezzanine_path: Path | None = None) -> ClipMeasurement`.
2. Implement CLI entrypoint (`python -m hawedit.measure`) supporting `--ass`, `--mezzanine`, `--out`, and `--json`.

### Task 5: Comprehensive Unit Tests (`tests/test_measure.py`)
1. `test_measure_reads_only_the_delivered_file`: AST analysis verifying `hawedit.measure` imports neither `render` nor `pipeline`.
2. `test_measure_probes_container_and_streams_accurately`: Probes fixture video and validates metadata against ground truth.
3. `test_measure_ebur128_loudness_and_silences`: Verifies loudness and silence gap calculations.
4. `test_measure_face_tracking_and_caption_ink`: Validates face and caption analysis.
5. `test_measure_cli_emits_valid_json`: Validates CLI execution and `<clip>.measured.json` output schema.

## Acceptance & Verification
- `bash scripts/verify.sh` runs lint, typecheck, format, and full test suite with 0 errors.
