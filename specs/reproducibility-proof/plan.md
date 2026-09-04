# Plan — Reproducibility Proof (`specs/reproducibility-proof`)

> Approved-by: Hawa (Task T1.7 from `specs/pro-grade-program/tasks.md`; autonomous directive `/goal make canon`)

## 1. Goal
Fulfill Task T1.7 of `specs/pro-grade-program/tasks.md` by demonstrating end-to-end reproducibility of HawEdit renders:
- ASS subtitles byte-identical across runs.
- Contract structures identical (minus timestamps).
- Video agreement PSNR >= 45 dB / VMAF >= 98 between two renders with pinned deliverable parameters.
- Provide automated unit/media test `test_two_renders_of_one_edit_agree`.
- Record Level B measurement on canonical media in `evidence/two-renders-of-one-edit.md`.

## 2. Work Breakdown

1. **Task T1: Automated Test (`test_two_renders_of_one_edit_agree`)**:
   - Add `test_two_renders_of_one_edit_agree` to `tests/test_render.py` using `FIXTURE` (`kurdish-speech-3cuts.mp4`).
   - Render two clips to separate temporary files with pinned deliverable parameters (`Encoder.NVENC` if available, else `Encoder.X264`).
   - Assert ASS byte identity.
   - Assert contract dictionary equality (omitting execution timestamps/clip ID).
   - Compute PSNR via FFmpeg `psnr` filter and assert `psnr >= 45.0` (or `inf`).

2. **Task T2: Canonical Real-Media Measurement & Evidence**:
   - Re-render canonical clip `ep29-VbX8UWwl1c4-s25-25` twice using pinned NVENC arguments on `HAWAPC01`.
   - Calculate PSNR and VMAF between the two canonical renders.
   - Author `evidence/two-renders-of-one-edit.md` containing all required headers (`commit:`, `media_sha256:`, `host:`, `command:`).

3. **Task T3: Verification & Ledger Update**:
   - Run verification gate (`bash scripts/verify.sh`).
   - Ratchet test floor if test count increased.
   - Update ledger via `scripts/update-ledger.sh reproducibility-proof T1 test_two_renders_of_one_edit_agree`.
   - Mark T1.7 as DONE in `specs/pro-grade-program/tasks.md`.
