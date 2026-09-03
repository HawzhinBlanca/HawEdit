# Specification — Two-Pass Linear Loudnorm (Task T3.1)

## Acceptance Criteria (EARS)

- **AC-1 (Pass 1 Audio Measurement)**:
  WHEN `measure_audio_loudness` is called with an audio or video source and time span,
  THE system SHALL execute FFmpeg in null-muxer mode with `loudnorm=...:print_format=json` and return a populated `LoudnessStats` containing valid float values for `input_i`, `input_tp`, `input_lra`, `input_thresh`, and `target_offset`.

- **AC-2 (Linear Audio Filter Formatting)**:
  WHEN `audio_filter(measured=stats, linear=True)` is called with valid `LoudnessStats`,
  THE system SHALL construct an FFmpeg audio filter string that incorporates `measured_I`, `measured_TP`, `measured_LRA`, `measured_thresh`, `offset`, `linear=true`, and `aresample=48000`.

- **AC-3 (Deliverable Render Two-Pass Execution)**:
  WHEN `render_clip` is invoked with `deliverable=True`,
  THE system SHALL execute Pass 1 analysis prior to video encode, apply linear loudnorm in Pass 2, and return `RenderResult` with both `loudness_pass1` and `loudness_pass2` populated.

- **AC-4 (Working Render Backwards Compatibility)**:
  WHEN `render_clip` is invoked with `deliverable=False` (default),
  THE system SHALL retain single-pass dynamic loudnorm and omit pass 1 measurement, maintaining exact backwards compatibility with existing test hashes and fast render times.

- **AC-5 (Contract Loudness Recording)**:
  WHEN a deliverable render with two-pass loudnorm completes in `pipeline.py`,
  THE system SHALL record `{"pass1": {...}, "pass2": {...}}` inside `clip.output.loudness`, serializing the full acoustic record into the delivered editing contract JSON.
