# Research: Real-Media Test Tier (`tests/media/`, Task T1.4)

## 1. Problem Statement & Specification (§7.1, §7.2, Task T1.4)
Existing tests in `tests/` operate on synthetic test clips (e.g., `tests/fixtures/kurdish-speech-3cuts.mp4`, 2.5s duration) or mock frames. Nothing in the automated test suite asserts properties against real 1440p multi-camera Kurdish media (`ep29-chunk50min.mp4`, 50 minutes, 2560x1440, multi-speaker podcast).

Task T1.4 establishes a dedicated `tests/media/` tier:
- Gated on environment variable `HAWEDIT_MEDIA_ROOT` and a pinned SHA256 of `ep29-chunk50min.mp4`:
  `47235f4251961518d9bbae1ecbda9c7f5166c5baa57a2be98f5ec0eb64e6f863`.
- Invariant: **Fails, never skips**, when `HAWEDIT_MEDIA_ROOT` is set and the media file is missing, corrupt, or has mismatched hash.
- Zero-skip compatibility: When `HAWEDIT_MEDIA_ROOT` is unset (e.g. on clean GitHub-hosted Ubuntu runners without 50-minute video), `tests/media/` must not emit `skipped` in the report so `--require-no-skips` passes cleanly.
- First tests:
  1. Face in 9:16 crop $\ge 90\%$ of speech frames.
  2. $\ge 1$ camera scene change per 8 seconds across the source material.
  3. No `scdet` cut event inside any aligned word boundary.
  4. Integrated speech loudness (EBU R128) conforms to $-14.0 \pm 1.0$ LUFS with true peak $\le -0.5$ dBTP.
  5. Caption-band ink energy verified on rendered media.
  6. First-frame face presence after hook card ($\ge 10\%$ face height share).
  7. Fixture provenance recorded in `tests/media/provenance.json`.

## 2. Existing Codebase Assets & Grounding
- `src/hawedit/measure.py`:
  - `measure_clip(clip_path, ass_path, sample_interval_ms=200)`: Independent AST-isolated ground-truth analyzer measuring width, height, fps, bitrate, EBU R128 (`integrated_lufs`, `true_peak_db`, `lra_lu`), silences, scene cuts (`scdet`), face tracking (`face_detected_share`, `first_frame_face_share`, `median_y_center_share`), and caption ink energy (`ink_energy_detected_share`).
- `src/hawedit/ingest.py`:
  - `detect_scenes_scdet(video_path)`: Native FFmpeg scene cut detector.
  - `detect_vad_silero(audio_path)`: Speech timestamp segment detector.
- `src/hawedit/boundary.py`:
  - Word timing constraints and scene cut avoidance.
- `src/hawedit/reframe.py`:
  - `OpenCVFaceTracker`: 5.0 fps Haar + CSRT tracking.
- `src/hawedit/delivery.py`:
  - Reconciliation clauses verifying measurement against contract.

## 3. Real Media Parameters
- Media path: `ep29-chunk50min.mp4` under `HAWEDIT_MEDIA_ROOT`.
- Pinned SHA-256: `47235f4251961518d9bbae1ecbda9c7f5166c5baa57a2be98f5ec0eb64e6f863`.
- Size: 1,029,910,217 bytes (~1.03 GB).
- Dimensions: 2560x1440, 25.0 fps, 50:00.00 duration.
- Source: Zar Podcast Episode #29 (Ayub Nuri).
