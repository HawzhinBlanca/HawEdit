# Tasks: E1 — Per-Reel Contact Sheet (`<clip_id>.contact-sheet.jpg`)

## Round 1 (Spec Commit)
- [x] T0.1 Audit `artifact_bundle.py`, `candidate_review.py`, `episode.py`, `pipeline.py`, `measure.py`, `edit_plan.py`, `captions.py`, `D:\HawEdit-media\contact-sheets\`, `tests/test_claims.py`, and `tests/test_vex.py`.
- [x] T0.2 Author `research.md`, `spec.md`, `plan.md`, `impact-map.md`, and `tasks.md`.

## Round 2 (Implemented on `gemini/lane-5` — Ledgers Flipped by Lead `update-ledger.sh`)
- [x] T1 (`E1-R1`..`E1-R5`): Create `tests/test_contact_sheet.py` generating synthetic two-color FFmpeg MP4 + `.ass` + `.edit_plan.json` reels and pipeline post-publish verification.
- [x] T2 (`E1-R1`..`E1-R5`): Implement `src/hawedit/contact_sheet.py` reusing `measure.py` (`probe_container`, `probe_scene_cuts`, `_parse_ass_dialogue_cues`), `edit_plan.VisualEditPlan`, `captions.find_ffmpeg()`, and `cli.use_utf8_streams()`.
- [x] T3 (`E1-R1`): Wire post-publish `render_reel_contact_sheet(...)` in `src/hawedit/pipeline.py` (`_render_episode_single_clip` and `run_pipeline`).
- [x] T4 (Docs): Add `contact_sheet.py` row to `README.md`, `PROGRESS.md` (`M9.41`), and `DECISIONS.md` (`D-353`), keeping `tests/test_claims.py` green.
