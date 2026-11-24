# Specification: E1 — Per-Reel Contact Sheet (`<clip_id>.contact-sheet.jpg`)

## Overview
Generate a single high-readability JPEG contact sheet (`<clip_id>.contact-sheet.jpg`) next to every delivered `.mp4` reel (and via standalone CLI `python -m hawedit.contact_sheet <reel.mp4>`), showing the first frame, both sides of every cut, and an enlarged caption crop.

## Constants & Defaults
- `CONTACT_SHEET_SUFFIX = ".contact-sheet.jpg"`
- `GRID_COLUMNS = 4`
- `MAX_CUT_PAIRS = 12` (caps pathological high-cut inputs cleanly while labeling if capped; normal 30–90 s podcast reels have 0–8 cuts)
- `CAPTION_BAND_RATIO = 0.34` (bottom 34% by default for standard bottom-aligned reels; top 34% when active ASS cue specifies `\an7`/`\an8`/`\an9`)

## EARS Acceptance Criteria

### E1-R1: Output path next to reel without breaking `ArtifactBundle`
- **WHEN** `render_reel_contact_sheet(mp4_path, ...)` succeeds for `path/to/clip_01.mp4`, **THE** module **SHALL** write the JPEG atomically next to the reel at `path/to/clip_01.contact-sheet.jpg` (`mp4_path.with_suffix(".contact-sheet.jpg")`, or explicit `--output` override) without adding `.contact-sheet.jpg` to `ArtifactBundle._SUFFIXES`.
- **WHEN** `pipeline.py` finishes `bundle.publish()` in `_render_episode_single_clip()` (`pipeline.py:2561-2569`) or single-clip `run_pipeline()` (`pipeline.py:4652`), **THE** pipeline **SHALL** generate `<clip_id>.contact-sheet.jpg` beside `<clip_id>.mp4` in `bundle.final_dir`.
- **Mapped tests (`tests/test_contact_sheet.py`):**
  - `test_contact_sheet_writes_beside_mp4_and_preserves_bundle_suffixes`
  - `test_pipeline_post_publish_generates_contact_sheet_next_to_reel`

### E1-R2: Required visual contents — first frame + pre/post cut pairs + enlarged caption crop
- **WHEN** a reel has `K >= 0` cut timestamps in output timeline coordinates, **THE** contact sheet generator **SHALL** extract:
  1. Tile 0: the **first frame** (`t = 0 ms`, labeled `FIRST 0.000s`),
  2. Tiles `1 .. 2K`: for each cut `k` at `cut_ms`, the **pre-cut frame** (`max(0, cut_ms - frame_ms)`, labeled `CUT #k PRE`) immediately paired with the **post-cut frame** (`cut_ms`, labeled `CUT #k POST`),
  3. Dedicated wide bottom strip: an **enlarged caption crop** (width = full sheet width, height scaled cleanly to preserve aspect) sampled from an active caption midpoint (or clip midpoint if no `.ass` cue exists, explicitly labeled on the tile).
- **WHEN** a reel has zero cuts (`K = 0`), **THE** generator **SHALL** still render the `FIRST` frame tile and enlarged `CAPTION CROP` strip cleanly without error.
- **Mapped tests (`tests/test_contact_sheet.py`):**
  - `test_contact_sheet_extracts_first_frame_both_sides_of_cuts_and_caption_crop`
  - `test_contact_sheet_zero_cut_reel_still_includes_first_and_caption_crop`

### E1-R3: Distinct visual capture across cut boundaries
- **WHEN** a synthetic two-color test reel has a hard visual cut at timestamp `C` (e.g., color A before `C`, color B from `C` onward), **THE** extracted `CUT #1 PRE` tile pixels **SHALL** match color A and the extracted `CUT #1 POST` tile pixels **SHALL** match color B (proving frame-accurate pre/post capture rather than off-by-one keyframe drift).
- **Mapped tests (`tests/test_contact_sheet.py`):**
  - `test_contact_sheet_pre_and_post_cut_frames_capture_distinct_sides_of_cut`

### E1-R4: Enlarged caption crop localization
- **WHEN** a sibling `.ass` file (or explicit `--ass`) contains Dialogue cues, **THE** generator **SHALL** parse active cue intervals via `measure._parse_ass_dialogue_cues()`, sample at the longest/first valid cue midpoint inside `[0, duration_ms]`, crop the active caption region (`CAPTION_BAND_RATIO`), and enlarge it relative to raw thumbnail width.
- **Mapped tests (`tests/test_contact_sheet.py`):**
  - `test_contact_sheet_caption_crop_targets_active_ass_midpoint_and_enlarges`

### E1-R5: Explicit grid filler and strict fail-stop behavior
- **WHEN** the 4-column tile row has unused trailing cells, **THE** generator **SHALL** fill unused cells with a labeled non-black filler block (`NO TILE`) so E2/human reviewers never confuse grid padding with dead video frames.
- **WHEN** the input `.mp4` does not exist, fails `probe_container`, has zero decodable frames, or FFmpeg/frame extraction returns an error, **THE** generator **SHALL** fail immediately (`RuntimeError` / `ValueError`, CLI non-zero exit) and MUST NOT write a partial output JPEG.
- **Mapped tests (`tests/test_contact_sheet.py`):**
  - `test_contact_sheet_marks_unused_grid_cells_as_filler`
  - `test_contact_sheet_fails_stop_on_missing_or_unreadable_video`
