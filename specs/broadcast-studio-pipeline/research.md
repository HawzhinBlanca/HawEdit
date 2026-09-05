# Research: Broadcast Studio Pipeline & Reel Aesthetic Overhaul

## 1. Grounding & Codebase Symbols
- **`src/hawedit/render.py`**:
  - `two_person_split_filter(source_width, source_height, top_crop, bottom_crop, target_width, target_height, ...)`: Implements stacked 9:8 vertical split (1080x960 top, 1080x960 bottom).
  - `vertical_crop_size(source_w, source_h, target_w, target_h)`: Computes base vertical crop dimensions.
  - `vertical_framing(source_height, crop_w, crop_h, face_center_y, face_height)`: Adjusts vertical crop window based on face composition line (`FACE_COMPOSITION_LINE = 0.38`).
  - `crop_filter(...)`: Builds FFmpeg crop filter.
  - `decide_wide_shot_layout(...)`: Evaluates whether wide shot should be cropped, zoomed, or blurred-fill.
  - `Reframe` enum: `STATIC_CENTRE`, `SMOOTH_CENTRE`, `SPEAKER_TRACKED`, `BLURRED_FILL`, `TWO_PERSON_SPLIT`.
- **`src/hawedit/reframe.py`**:
  - `compute_two_person_split_crops(source_width, source_height, speaker1_center_x, speaker2_center_x, ...)`: Produces (x1, y1, w1, h1) and (x2, y2, w2, h2) for two speakers.
  - `detect_rapid_speaker_exchange(...)`: Detects rapid speaker alternation.
- **`src/hawedit/captions.py`**:
  - `build_ass(...)`: Generates ASS subtitle format.
  - `CaptionStyle` enum: `LINE`, `WORD_HIGHLIGHT`, `VIRAL_POPUP`, `RTL_WORD_HIGHLIGHT`.
  - MarginV currently defaults to 160px or 200px, which places subtitles too low on 1920h canvas (near 1720px - 1760px), overlapping lower third elements and bottom UI bars.
- **`src/hawedit/brand.py`**:
  - `BrandKit`: Holds logo, progress bar, speaker metadata, end card.
  - `build_speaker_tag_events(...)`: Generates ASS Dialogue layer 2 lower-third speaker plates.
  - `build_end_card_events(...)`: Generates ASS Dialogue layer 3 closing CTA cards.
- **`src/hawedit/pipeline.py`**:
  - `run_pipeline(...)`: Main orchestration runner.
  - CLI argument parser binds `--caption-style`, `--split-screen`, `--brand-kit`, etc.

## 2. Root Cause Analysis of Deficiencies
1. **Vertical Subtitle Position**:
   - In `agency_frame_02`, subtitle is at bottom margin ~160px (Y ≈ 1760).
   - This places text right on top of table props (tea cup, table rim).
   - In standard 1080x1920 mobile reels, the optimal subtitle band is Y = 1350 to 1450 (`MarginV` = 460 to 520px). This keeps captions at chest height, clear of phone UI and table clutter.
2. **Wide Shot Composition**:
   - `agency_frame_03` and `agency_frame_04` cropped full source height (1440px), resulting in 810x1440 crop window.
   - For a wide shot, this includes chair wheels, table legs, and excessive ceiling, making human subjects look tiny and lost.
   - Solution: Either (a) Tighter upper-body framing (zoom factor 1.35x - 1.5x) or (b) Two-person stacked split-screen where host is top pane and guest is bottom pane.
3. **Logo Tofu Boxes**:
   - `zar_logo.png` had unrendered font glyphs (`[][][][][]`). Needs clean vector/rendered badge without missing font dependencies.
4. **Speaker Lower-Third Badge**:
   - The current speaker tag is a raw black bounding box at the bottom edge.
   - Needs agency-grade styling: pill-shaped translucent badge, gold brand accent, clear Kurdish typography, placed at safe Y level.
