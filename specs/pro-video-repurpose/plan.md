# Plan — Pro Video Repurposing: Elevating HawEdit to Top-Tier Output

> **Goal:** Close the quality and aesthetic gap between HawEdit and the industry Top 3 (Opus Clip, Submagic, Klap) by integrating the 5 essential finishing techniques that create a truly perfect, viral 9:16 Kurdish short reel.

## Status
Approved-by: Pending human approval

---

## Tasks

### Task 0: Gate Floor Restoration (`tests/test_broadcast_studio.py`)
- Merge the 11 previously missing regression tests with the 6 new broadcast preset tests in `tests/test_broadcast_studio.py`.
- Ensure all 23 tests pass cleanly and the gate test count floor ($\ge 3,572$) is green.

### Task 1: Dynamic Kinetic Word "Pop" Subtitles (`CaptionStyle.KINETIC_POP`)
- In `src/hawedit/captions.py`:
  - Add `CaptionStyle.KINETIC_POP = "kinetic_pop"`.
  - In `_build_ass_from_words`, apply dynamic word scaling using ASS override tags:
    `{\t(0, 70, \fscx115\fscy115)\t(70, 140, \fscx100\fscy100)\c&H00FFFF00&}` on the active word, with trailing words in high-contrast white.
  - Preserve HarfBuzz complex Arabic cursive shaping without word separation bugs.

### Task 2: 0–3s Sticky Hook Headline Banner (`--hook-banner`)
- In `src/hawedit/captions.py` and `src/hawedit/pipeline.py`:
  - Add `HookBannerConfig` supporting top-center placement (`Alignment 8`, `MarginV 120`).
  - Automatically extract or format a punchy Sorani hook headline (from Gemini verdict `title_ckb` or user override).
  - Render with a dark translucent pill plate (`border_style=3`, `OutlineColour=&H80000000`) for the first 3.5 seconds, fading in (`150ms`) and fading out (`300ms`).

### Task 3: Background Music Bed with Auto-Sidechain Ducking (`--music-bed`)
- In `src/hawedit/render.py`:
  - Add `music_bed_path: Path | None = None` and `music_bed_ducking_db: float = -20.0` to `render_clip`.
  - Implement native FFmpeg audio filtergraph using `sidechaincompress`:
    `[dialogue]asplit=2[dia_out][dia_sc];[music][dia_sc]sidechaincompress=threshold=0.04:ratio=6:attack=50:release=400[ducked_music];[dia_out][ducked_music]amix=inputs=2:weights=1.0 0.25[aout]`.
  - Provide curated royalty-free tension/ambient podcast audio loop in `work/assets/music_tension_bed.wav`.

### Task 4: Multi-Cam Two-Person Stacked Split-Screen in Pipeline (`--two-person-split auto`)
- In `src/hawedit/pipeline.py`:
  - Add `--two-person-split {auto,always,never}` to argument parser.
  - Wire `two_person_split_filter` from `render.py` into the execution path:
    - When diarization indicates rapid dialogue turns (< 3.0s) between 2 tracked speakers, automatically select `Reframe.TWO_PERSON_SPLIT`.
    - Stack Host (top 1080x960) and Guest (bottom 1080x960) with clean separation.

### Task 5: Contextual B-Roll Overlay (`--b-roll`)
- In `src/hawedit/render.py`:
  - Support optional entity B-roll image/video cutaway overlay (e.g. historical portrait of Paul Bremer during the Bremer turn).
  - Render with subtle Ken Burns zoom (`1.00x -> 1.06x`) for 2.5s with 200ms crossfade.

### Task 6: Automated Testing & Reference Master Render
- Add unit and integration tests in `tests/test_pro_video_repurpose.py`.
- Run full gate: `bash scripts/verify.sh` to ensure 100% green pass.
- Render the definitive, agency-grade short reel from Zar Podcast Ep 29 (`work/ep29_perfect_short_master.mp4`) with all 5 features enabled.
- Generate contact sheet and inspect keyframes.
