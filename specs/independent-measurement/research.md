# Research — Independent Measurement Module (`hawedit.measure`)

## 1. Problem & Threat Model

### 1.1 The Proof Gap
In `research.md` (§5, §7), the audit demonstrated that the existing test suite asserts **intent rather than outcome**:
- `captions_burned_in=True` is an unconditional constant set by the code that rendered the clip (`render.py:874`).
- `RenderResult.width` and `height` are constants (`render.py:866-867`), not probed from the encoded container.
- `FACE_TRACKED` is assigned if any focus points were provided (`pipeline.py:2301-2311`), even if the resulting vertical crop shows an empty table or the rug.
- `silence_removed_ms` is declared in the contract (`clip.py:495`), even though `silence.py` has no callers in `src/`.
- Loudness is tested only on synthetic sine waves, not on the actual delivered multi-stream MP4.

### 1.2 The Independence Principle (Proof Standard Level B & C)
A renderer cannot grade itself. To establish true verification:
1. **Zero Access to Internal State**: The measurement module must run as an independent process or isolated module with zero imports of `hawedit.render` or `hawedit.pipeline`.
2. **Pixel & Stream Reality**: All measurements must be derived strictly from the bytes of the delivered artifact (`.mp4`, `.ass`, `.srt`).
3. **Standard Tooling**: Derivation relies entirely on platform standard tools (`ffprobe`, `ffmpeg` filters `ebur128`, `scdet`, `silencedetect`, and OpenCV `cv2`), requiring no new heavy dependencies.

---

## 2. Measurement Capabilities & Filter Graphs

### 2.1 Container & Video Stream Inspection
- **Tool**: `ffprobe -v error -show_entries format=duration,size,bit_rate:stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,pix_fmt,color_space,color_transfer,color_primaries -of json <mp4>`
- **Extracted Properties**:
  - `duration_ms`: Exact media container and stream duration.
  - `width` × `height`: e.g. 1080×1920.
  - `fps`: Exact fractional rational (e.g. 25/1, 30000/1001) and floating point value.
  - `frames_count`: Total frame count.
  - `bitrate_kbps`: Measured stream and format bitrates.
  - `codec`: e.g. `h264` / `hevc`.
  - `pix_fmt`: e.g. `yuv420p`.
  - `color_tags`: `bt709` / `bt601` colour space, transfer, and primaries.
  - `sha256`: SHA-256 checksum of the delivered file.

### 2.2 Scene Cut Detection (`scdet`)
- **Command**: `ffmpeg -i <mp4> -vf "select='gt(scene,0.3)',showinfo" -f null -`
- **Output Parsing**: Extract `pts_time` timestamps for every visual shot transition.
- **Verification Purpose**: Compare detected visual cuts against Stage 0 source cuts and planned punch-in zoom timestamps.

### 2.3 Audio Loudness & Dynamics (`ebur128`)
- **Command**: `ffmpeg -i <mp4> -af "ebur128=peak=true:framelog=verbose" -f null -`
- **Output Parsing**:
  - Integrated Loudness: `I` (LUFS, targeting −14.0 ± 0.5 LUFS).
  - True Peak: `TP` (dBFS, targeting ≤ −1.0 dBFS).
  - Loudness Range: `LRA` (LU, measuring compression/dynamics).

### 2.4 Silence Detection (`silencedetect`)
- **Command**: `ffmpeg -i <mp4> -af "silencedetect=noise=-30dB:d=0.25" -f null -`
- **Output Parsing**:
  - Sequence of `[silence_start, silence_end]` intervals in milliseconds.
  - Total dead-air duration (ms) and percentage of clip duration.
  - Longest continuous pause duration.

### 2.5 Face Detection & Framing Analysis (OpenCV Haar/DNN)
- **Method**: Sample video at 5 fps using `cv2.VideoCapture` and detect face bounding boxes `(x, y, w, h)` via Haar cascades (`haarcascade_frontalface_default.xml`, `haarcascade_profileface.xml`).
- **Computed Metrics**:
  - Per sample: timestamp `t_ms`, bounding box `[x, y, w, h]`, face height share `h / frame_height`, vertical center share `(y + h/2) / frame_height`.
  - Summary: `face_detected_frame_share` (percentage of speech frames with detected face), `median_face_height_share`, `median_y_center_share`.
  - Invariant Verification: Verifies whether the subject stays on the `0.38` composition line and whether face share is adequate (preventing wide-shot table/rug framing).

### 2.6 Caption Band Ink Energy & Legibility
- **Method**:
  - Read dialogue cue timings from the `.ass` / `.srt` file.
  - In each caption event, sample video frames in the designated caption band (vertical region `[0.65..0.90]` of frame height).
  - Compute spatial gradient magnitude (Sobel / Laplacian variance) within the caption band during subtitle cues vs non-subtitle baseline frames.
  - Compute luminance contrast ratio between candidate text regions (brightest 10% in caption band) and local background (surrounding pixels) to verify WCAG legibility (≥ 4.5:1).
- **Computed Metrics**:
  - `caption_events_count`: Number of subtitle cues.
  - `ink_energy_detected_share`: Share of subtitle events exhibiting clear burned-in text ink energy (target ≥ 95%).
  - `median_contrast_ratio`: Median text-to-background contrast.

### 2.7 Video Quality Assessment (Optional Mezzanine VMAF/PSNR)
- **Command**: When a lossless mezzanine `<clip>.mezzanine.mp4` exists:
  `ffmpeg -i <mp4> -i <mezzanine> -lavfi "[0:v][1:v]libvmaf=model=version=vmaf_v0.6.1:log_fmt=json" -f null -`
- **Output**: VMAF score (target ≥ 93) and PSNR (dB).

---

## 3. Schema & Output Artifact: `<clip>.measured.json`

The measurement module outputs a structured JSON document:
```json
{
  "schema": 1,
  "file": {
    "path": "work/ep29-VbX8UWwl1c4-s25-25/ep29-VbX8UWwl1c4-s25-25.mp4",
    "sha256": "3a81...",
    "size_bytes": 21106780
  },
  "video": {
    "width": 1080,
    "height": 1920,
    "fps": 25.0,
    "fps_ratio": "25/1",
    "duration_ms": 56600,
    "frames_count": 1415,
    "bitrate_kbps": 2790.5,
    "codec": "h264",
    "pix_fmt": "yuv420p",
    "color_space": "bt709",
    "color_transfer": "bt709",
    "color_primaries": "bt709"
  },
  "audio": {
    "codec": "aac",
    "sample_rate": 48000,
    "channels": 2,
    "duration_ms": 56600,
    "integrated_lufs": -14.2,
    "true_peak_db": -1.0,
    "lra_lu": 2.2,
    "silences": [
      {"start_ms": 5120, "end_ms": 5480, "duration_ms": 360}
    ],
    "total_silence_ms": 6720,
    "silence_share": 0.119
  },
  "scenes": {
    "cuts_ms": [560, 11040, 17080, 20840, 26000, 34240, 39680, 44640, 47680, 55640]
  },
  "faces": {
    "sample_interval_ms": 200,
    "samples_count": 283,
    "face_detected_frames_count": 255,
    "face_detected_share": 0.901,
    "median_face_height_share": 0.185,
    "median_y_center_share": 0.382
  },
  "captions": {
    "events_count": 24,
    "ink_energy_detected_share": 1.0,
    "median_contrast_ratio": 6.8
  },
  "vmaf": null,
  "tool_metadata": {
    "ffmpeg_version": "8.1.1-full",
    "measured_at": "2026-09-02T17:15:00Z"
  }
}
```

---

## 4. Architectural Boundaries & Invariants

1. **AST Independence**: `src/hawedit/measure.py` must NEVER import `hawedit.render` or `hawedit.pipeline`. A dedicated AST-level unit test `test_measure_reads_only_the_delivered_file` validates this constraint in CI.
2. **Pure Subprocess Capability**: Can be invoked from CLI as `python -m hawedit.measure <clip.mp4>` or programmatically as `measure_clip(path, ...) -> ClipMeasurement`.
3. **No Network / External API Dependencies**: Derives all information locally via ffmpeg and OpenCV.
4. **Deterministic and Reproducible**: Derives the exact same measurements given the same delivered media file.
