# Specification — Reproducibility Proof (`specs/reproducibility-proof`)

## Acceptance Criteria (EARS Format)

- **AC-1 (Subtitle Determinism)**:
  - WHEN generating subtitle files from identical sentence/word timing inputs,
  - THE system SHALL produce byte-identical ASS files (`ass1.read_bytes() == ass2.read_bytes()`).

- **AC-2 (Contract Determinism)**:
  - WHEN compiling clip contract models from identical pipeline inputs,
  - THE system SHALL produce identical contract data structures excluding execution-dependent timestamps (`rendered_at`, `tool_metadata.measured_at`) and output path references.

- **AC-3 (Render Video Agreement)**:
  - WHEN encoding two renders of the same edit with pinned deliverable parameters,
  - THE system SHALL achieve video PSNR >= 45.0 dB (or `inf` if bit-exact) and VMAF >= 98.0 across all frames.

- **AC-4 (Pinned Encode Arguments)**:
  - WHEN executing deliverable renders on NVENC or libx264,
  - THE system SHALL pin preset, profile, GOP keyint, B-frames, and AQ flags so the encoding parameters are fully specified.
