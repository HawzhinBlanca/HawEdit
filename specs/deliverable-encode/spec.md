# Specification — Deliverable Encode Profile (`specs/deliverable-encode`)

## Acceptance Criteria (EARS Format)

- **AC-1 (NVENC Deliverable Args)**:
  - WHEN encoding with `Encoder.NVENC` in deliverable mode,
  - THE system SHALL specify `-preset p6 -profile:v high -bf 3 -spatial-aq 1 -temporal-aq 1 -rc vbr -cq <crf> -b:v 0 -g <2*fps>`.

- **AC-2 (libx264 Deliverable Args)**:
  - WHEN encoding with `Encoder.X264` in deliverable mode,
  - THE system SHALL specify `-preset slow -profile:v high -bf 3 -crf <crf> -g <2*fps>`.

- **AC-3 (Color Primaries & Metadata Tags)**:
  - WHEN generating video encoding arguments for MP4 delivery,
  - THE system SHALL include `-color_primaries bt709 -color_trc bt709 -colorspace bt709`.

- **AC-4 (Lanczos Scaling & Light Unsharp)**:
  - WHEN constructing the video filter chain in `crop_filter`,
  - THE system SHALL scale with `flags=lanczos` and apply light unsharp sharpening (`unsharp=5:5:0.5:5:5:0.0`).

- **AC-5 (Parallel Decode Multi-threading)**:
  - WHEN executing ffmpeg subprocess in `render_clip`,
  - THE system SHALL NOT pass `-threads 1` on input decoding.
