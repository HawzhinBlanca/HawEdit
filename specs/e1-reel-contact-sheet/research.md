# Research: E1 — Per-Reel Contact Sheet (`<clip_id>.contact-sheet.jpg`)

## 1. Goal & Scope
Phase E1 (`specs/pro-grade-program/gemini-task-sheet-2026-11-18.md`) requires generating a contact sheet per rendered reel containing:
1. **First frame** (`0 ms`),
2. **Both sides of every cut** (pre-cut last frame before each cut, post-cut first frame at each cut),
3. **An enlarged caption crop** so Kurdish glyphs, RTL flow, karaoke highlight contrast, and bottom/top safe-margin framing are legible in one glance without scrubbing.

Saved directly next to each delivered reel (`<stem>.contact-sheet.jpg`). Must run on CPU (`CUDA_VISIBLE_DEVICES=""`) using pinned repo tools. Round 1 covers **research + spec/plan only**.

## 2. Codebase & Artifact Audit

### 2.1 Existing contact sheets in `D:\HawEdit-media`
Inspected `D:\HawEdit-media\README.md:1-63` and `D:\HawEdit-media\contact-sheets\`:
- Source preview contact sheets already exist for long source clips (e.g., `zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.jpg` at `1600×540` 3×5 grid; `opening.jpg` sheets at `1920×720`), covering broad source inspection.
- No per-reel post-render contact sheet currently exists in `src/hawedit/` or alongside rendered reels.

### 2.2 Delivery bundle invariants (`artifact_bundle.py`, `candidate_review.py`, `episode.py`, `pipeline.py`)
Audited how sidecar files are validated and published:
- `src/hawedit/artifact_bundle.py:25` fixes `_SUFFIXES: Final = ("ass", "mp4", "srt", "edl", "json", "measured.json", "edit_plan.json")`, and `ArtifactBundle._validate()` (`src/hawedit/artifact_bundle.py:243-270`) **rejects any unexpected suffix** inside the atomic staging directory before publish.
- `src/hawedit/candidate_review.py:29` mirrors `REVIEW_SUFFIXES = ("mp4", "ass", "srt", "edl", "json", "measured.json", "edit_plan.json")`.
- `src/hawedit/pipeline.py:2058-2078` (`_ensure_clip_cover_image`) and `pipeline.py:2561-2569` (`_render_episode_single_clip`) write `<clip_id>.cover.png` into `bundle.final_dir` **after** `bundle.publish()` (note: `episode.py:550-558` consumes `.cover.png`, whereas single-clip `run_pipeline()` at `pipeline.py:4652` currently skips cover creation).
- **Design implication:** Adding `.contact-sheet.jpg` to `ArtifactBundle._SUFFIXES` or `candidate_review.REVIEW_SUFFIXES` would break staging-contract tests unless all review/bundle modules were rewritten. Generating `<clip_id>.contact-sheet.jpg` in `bundle.final_dir` immediately after `bundle.publish()` in **both** `_render_episode_single_clip` (`pipeline.py:2561-2569`) and `run_pipeline` (`pipeline.py:4652`), plus exposing `python -m hawedit.contact_sheet <reel.mp4>`, covers every pipeline reel and every standalone reel cleanly without disturbing `ArtifactBundle` or `candidate_review` invariants.

### 2.3 Reusable codebase primitives (`ponytail` check)
- **`captions.find_ffmpeg()`** (`src/hawedit/captions.py`) + pinned FFmpeg (`AGENTS.md`): Available on Windows without PATH assumptions and decodes VP9/H.264 reliably via exact seek/frame-index extraction (`-ss` / `ffprobe` / `ffmpeg`).
- **`measure.py`** (`probe_container`, `probe_scene_cuts`, `_parse_ass_dialogue_cues`): Already parses ASS dialogue timestamps/text from `.ass` files and runs independent FFmpeg scene-cut detection (`probe_scene_cuts`) plus container metadata (`fps`, `duration_ms`).
- **`edit_plan.VisualEditPlan`** (`src/hawedit/edit_plan.py:324-573`): Holds exact `SourceTimeMapping` / output-timeline intervals (`clip_in_ms`, `clip_out_ms`, `retained_intervals_ms`) serialized to `<clip_id>.edit_plan.json`. From those mapped segments, every internal cut timestamp in output reel coordinates is exact to the millisecond without guessing.
- **`cli.use_utf8_streams()`** (`src/hawedit/cli.py:1-82`): Handles Windows UTF-8 console output.
- **OpenCV (`cv2`) / `numpy`**: Already imported in `src/hawedit/render_critic.py` for frame decoding (`VideoCapture`), resizing, and JPEG encoding; exact frame-accurate extraction paired with pinned FFmpeg or sequential decode avoids keyframe seek drift on compressed streams.

### 2.4 Living docs & test harness guardrails
- `tests/test_claims.py:496-505, 730-745`: Adding `src/hawedit/contact_sheet.py` requires entries in `README.md` (`L580-752`) and `PROGRESS.md` (`L1250-1314`).
- `tests/test_claims.py:1363-1406, 1655-1668`: Do **not** add a 17th `[project.scripts]` entry in `pyproject.toml`; expose `python -m hawedit.contact_sheet`.
- `tests/test_vex.py:27-30, 140-163`: Adding `src/hawedit/contact_sheet.py` changes `package_digest(src/hawedit)` and requires Lane 1's A3 VEX update or owner re-pin of `security/wsl-asr-vex.json` + `tests/test_vex.py`.

## 3. Technical Edge Cases Found
1. **Cut-source accuracy:** When `.edit_plan.json` (or `VisualEditPlan` / `SilencePlan` / `AssemblySpan`) is available, internal output cut timestamps are exact. When running standalone on an existing `.mp4` with no `.edit_plan.json`, falling back explicitly to `measure.probe_scene_cuts()` discovers visual cut boundaries; however, a single-shot reel with zero cuts must still produce a valid contact sheet containing `[FIRST FRAME]` + `[CAPTION CROP]` (never crashing on empty `cuts`).
2. **Pre-cut vs. post-cut frame selection:** At cut timestamp `cut_ms` with frame duration `frame_ms = 1000.0 / fps`, the last frame before the cut is `max(0.0, cut_ms - frame_ms)` (or `frame_index - 1`) and the first frame after the cut is `min(duration_ms - frame_ms, cut_ms)`. Seeking by exact frame index or accurate FFmpeg seek avoids showing two identical post-cut frames.
3. **Black-frame vs. grid-filler ambiguity:** Previous work (`DECISIONS.md` `D-333` / `specs/visual-editor-intelligence/research.md`) showed that unlabelled black padding cells can be misread by visual critics as dead/black rendered frames. Any unused cell in a 4-column grid MUST be clearly distinct (e.g., muted dark-slate filler tile explicitly stamped `FILLER / NO TILE`) and header-stamped tiles (`FIRST`, `CUT #k PRE`, `CUT #k POST`, `CAPTION CROP`).
4. **Enlarged caption crop localization:** Burned-in Sorani karaoke subtitles live in the bottom band (default ASS bottom alignment) or top band (`\an7`-`\an9`). Extracting the caption crop from a frame containing an active ASS cue midpoint (from `.ass` via `measure._parse_ass_dialogue_cues`)—cropping the caption band (e.g. bottom 32% of height across full width, or top 32% if ASS indicates top alignment) and upscaling cleanly (≥ 2× width) into a dedicated wide strip across the bottom of the contact sheet—keeps every Arabic glyph, diacritic, and word highlight readable at a glance.
5. **Fail-stop on unreadable/corrupt reels:** If the `.mp4` does not exist, fails `probe_container`, or yields zero decodable frames, fail immediately (`RuntimeError` / `ValueError`, non-zero exit), never writing a partial or placeholder JPEG.
