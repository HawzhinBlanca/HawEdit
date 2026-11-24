# Plan: E1 — Per-Reel Contact Sheet (`<clip_id>.contact-sheet.jpg`)

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"

## 1. Architecture & Minimal Design (`ponytail`)
Implement one lean CPU-only module `src/hawedit/contact_sheet.py` and wire post-publish generation into `pipeline.py` so every delivered reel gets `<clip_id>.contact-sheet.jpg` right next to `<clip_id>.mp4`:

1. **Cut & Caption Timestamp Resolution (Zero Duplicate Parsers):**
   - Prefer declared output-timeline cut points derived from `VisualEditPlan` (`.edit_plan.json` if sibling file exists or passed directly from `pipeline.py`) by collecting interior segment boundaries (`[seg_0.out_end, ...]`).
   - If no `VisualEditPlan` / `.edit_plan.json` is supplied in standalone CLI mode (`python -m hawedit.contact_sheet reel.mp4`), run `measure.probe_scene_cuts(mp4_path)` directly (explicit scene-cut mode for standalone inspection; fail-stop if probing fails).
   - Resolve active caption timestamp using `measure._parse_ass_dialogue_cues()` on sibling `<clip>.ass` (or `--ass`), selecting the midpoint of the first non-trivial cue (falling back to `duration_ms // 2` only when no `.ass` exists in standalone mode, visibly noted in the strip banner; when an `.ass` exists with zero parseable cues or all empty, report explicitly or fail-stop when strict mode requested).

2. **Frame-Accurate Extraction & Sheet Composition (CPU, Pinned FFmpeg + `cv2`/`numpy`):**
   - Extract target timestamps via pinned FFmpeg (`captions.find_ffmpeg()`, accurate `-ss` before `-i` with `vframes 1` into raw/PNG bytes decoded by `cv2.imdecode`, or single-pass sequential frame index grab) so VP9/H.264 pre-cut (`cut_ms - frame_ms`) and post-cut (`cut_ms`) frames never collapse onto the same keyframe.
   - Composite a 4-column grid of portrait thumbnails (e.g., `270×480` per tile + crisp dark header bar per tile with `FIRST`, `CUT #k PRE @ ...s`, `CUT #k POST @ ...s`) and explicit dark-slate `FILLER` cells for unused trailing grid slots.
   - Append a full-width (`1080 px` across all 4 columns) **Enlarged Caption Crop** strip at the bottom containing the cropped caption band (`CAPTION_BAND_RATIO = 0.34`, upscaled cleanly across full 4-column width with labeled timestamp and source mode), saved atomically (`tmp -> replace`) as `<clip_id>.contact-sheet.jpg`.

3. **Pipeline & Standalone CLI Integration:**
   - Call `render_reel_contact_sheet(...)` in `pipeline.py` immediately after `bundle.publish()`:
     - `_render_episode_single_clip` (`pipeline.py:2561-2569`, beside `_ensure_clip_cover_image`),
     - Single-clip `run_pipeline` (`pipeline.py:4652`).
   - Do **not** alter `ArtifactBundle._SUFFIXES` (`artifact_bundle.py:25`) or `candidate_review.REVIEW_SUFFIXES` (`candidate_review.py:29`).
   - Expose `python -m hawedit.contact_sheet <reel.mp4> [--ass ...] [--edit-plan ...] [--out ...]` (no extra `[project.scripts]` entry in `pyproject.toml`).

## 2. Files to Create or Modify in Round 2 (After Approval)
| Action | File | Purpose |
|---|---|---|
| Create | `src/hawedit/contact_sheet.py` | Cut/caption timestamp resolution, frame-accurate extraction, 4×N grid + enlarged caption strip, CLI |
| Edit | `src/hawedit/pipeline.py` (`:2561-2569`, `:4652`) | Post-publish generation of `<clip_id>.contact-sheet.jpg` next to `<clip_id>.mp4` |
| Create | `tests/test_contact_sheet.py` | Real synthetic FFmpeg-generated test reels verifying E1-R1..E1-R5 |
| Edit (integration) | `README.md`, `PROGRESS.md` | Module table + ledger row per `tests/test_claims.py:496-505, 730-745` |
| Coordinate | `security/wsl-asr-vex.json`, `tests/test_vex.py` | Re-pin or wait for A3 VEX parking (`tests/test_vex.py:140-163`) |

## 3. Verification Plan (Round 2)
1. `.venv\Scripts\python.exe -m pytest tests/test_contact_sheet.py tests/test_artifact_bundle.py tests/test_candidate_review.py tests/test_claims.py -q`
2. Run standalone CLI on an existing non-GPU test reel (or synthetic reel) to visually verify JPEG layout dimensions and readability (`D:\HawEdit-media\` never modified inside `sources/`).
3. `& "C:\Program Files\Git\bin\bash.exe" scripts/verify.sh --fast`

## 4. Open Questions / Risks
- **Lane merge coordination:** `pipeline.py` is also touched by other lanes (`pipeline.py:2561-2569` and `:4652` are narrowly scoped post-publish hooks).
- **ADR allocation:** Proposed ADR `D-353` can record placing `<clip_id>.contact-sheet.jpg` post-publish outside `ArtifactBundle._SUFFIXES` alongside `.cover.png` (`pipeline.py:2058-2078`).
