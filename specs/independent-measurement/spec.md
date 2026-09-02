# Spec — Independent Measurement Module (`hawedit.measure`)

## Acceptance Criteria (EARS Format)

- **CRITERION-1 (Container & Stream Inspection)**: WHEN measuring a media file, THE `measure` module SHALL extract exact video and audio stream properties (`width`, `height`, `fps`, `duration_ms`, `frames_count`, `bitrate_kbps`, `codec`, `pix_fmt`, `color_space`, `sha256`) using `ffprobe` directly from the delivered artifact.
- **CRITERION-2 (Audio Loudness & Dynamics)**: WHEN measuring audio tracks, THE `measure` module SHALL execute `ebur128` to extract Integrated Loudness (`I` LUFS), True Peak (`TP` dBFS), and Loudness Range (`LRA` LU), and execute `silencedetect` to extract all pause intervals.
- **CRITERION-3 (Scene Cut & Face Tracking Verification)**: WHEN analyzing video frames, THE `measure` module SHALL detect scene cut timestamps using `scdet`/`select` and compute face framing statistics (`face_detected_share`, `median_face_height_share`, `median_y_center_share`) sampled at ≥ 5 fps.
- **CRITERION-4 (Caption Ink Energy & Legibility)**: WHEN verifying subtitle delivery, THE `measure` module SHALL measure spatial high-frequency edge energy and luminance contrast within the caption band during subtitle cues.
- **CRITERION-5 (AST Independence)**: WHEN statically inspecting `hawedit.measure`, THE AST analysis SHALL verify that `hawedit.measure` contains zero imports of `hawedit.render` or `hawedit.pipeline`.
- **CRITERION-6 (Structured Output & CLI)**: WHEN invoked via CLI or API, THE `measure` module SHALL emit a validated `<clip>.measured.json` document conforming to schema 1.
