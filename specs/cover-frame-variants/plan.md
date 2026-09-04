# Implementation Plan — Cover Frame and Title Variants (Task T4.10)

## Objective
Implement automatic cover thumbnail selection (`cover.png`) based on face share, image sharpness, and open-eyes heuristic, along with Kurdish title variants (`title_variants_ckb`) for social media A/B testing, integrating seamlessly into `Clip.output` and `delivery.py`.

Approved-by: Hawa (pro-grade program autonomous mandate /goal)

## Steps
1. **Module Creation (`src/hawedit/cover.py`)**:
   - Create `src/hawedit/cover.py` with:
     - `score_cover_frame(frame, time_ms, ...)`
     - `select_cover_frame(video_path, output_png_path, ...)`
     - `generate_title_variants(base_title_ckb, hook_type)`
2. **Contract Extensions**:
   - Update `Output` in `src/hawedit/clip.py` to add `title_variants_ckb` and `cover_frame_ms`.
   - Update `JudgeVerdict` in `src/hawedit/judge.py` to add `title_variants_ckb`.
3. **Delivery Bundle Updates (`src/hawedit/delivery.py`)**:
   - Update `publish_delivery_bundle` to accept and write `cover.png`.
   - Update `reconcile_delivery` to validate `cover_frame_ms` boundary.
4. **Metadata & Ledger**:
   - Register `cover.py` in `README.md` and `PROGRESS.md` (`M9.27`).
   - Update `security/wsl-asr-vex.json` package digest.
5. **Testing & Real Media Reality Checks**:
   - Implement `tests/test_cover.py` covering all acceptance criteria.
   - Run cover selection on real media (`work/ep29-VbX8UWwl1c4-s25-25/ep29-VbX8UWwl1c4-s25-25.mp4`).
   - Generate `evidence/cover-selection-ep29.md`.
6. **Gate Verification & Ledger Flip**:
   - Run `scripts/verify.sh`.
   - Flip tasks via `scripts/update-ledger.sh cover-frame-variants T1 ...` and `T2 ...`.
