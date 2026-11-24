# Plan — Phone-readable captions off faces, tables, and burned-in teaser label (D5 / d5-phone-readable-captions)

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"

Read `research.md` and `spec.md` first. Captures: `captures/grid_d5_sizes.jpg`, `captures/teaser_and_table_boxes.jpg`, `captures/probe_d5.py.txt`.

## Approach

1. **Phone-readable defaults (`src/hawedit/captions.py`, `src/hawedit/assembly.py`, `src/hawedit/pipeline.py`)**:
   - `VIRAL_FONT_SIZE = 128` (`72 px` rendered ink height in `Vazirmatn`, `2.06×` of `64 pt` `35 px`).
   - `VIRAL_THEME`: `outline = 6.0`, `shadow = 2.0`, `margin_v = 450` (`y_center ≈ 1405 px`, lower-middle safe zone above platform UI chrome and above the `y = 1525..1734` `"لەم پۆدکاستەدا:"` pill).
   - `POPUP_MAX_CHARS = 20` (reconciled with `sanity_gate.py:140` `max_chars <= 20`), keeping `POPUP_MAX_WORDS = 3` and passing `max_popup_width_px = POPUP_MAX_WIDTH_PX` (`700`) in `pipeline.py:2410, 4300` and `assembly.py:308`.
   - `assembly.py:308` (`render_assembled_reel`) updated to pass `font_size=VIRAL_FONT_SIZE`, `theme=VIRAL_THEME`, `max_chars_per_line=POPUP_MAX_CHARS`, `max_words_per_event=POPUP_MAX_WORDS`, `max_popup_width_px=POPUP_MAX_WIDTH_PX`.
2. **Protected regions for faces, tables, and burned-in teaser label (`src/hawedit/shot_plan.py`, `src/hawedit/caption_layout.py`)**:
   - Add `ProtectedRegionKind.TABLE_OBJECT = "table_object"` to `shot_plan.py:45`.
   - Add optional `start_ms: int | None = None` and `end_ms: int | None = None` to `ProtectedContentRegion` (`shot_plan.py:57`), backward-compatible with all existing `ProtectedContentRegion` callers.
   - Update `caption_layout.py`: set `BOTTOM_BAND_BOX = (0.05, 0.70, 0.95, 0.80)` (matching `margin_v = 450` lower-middle band), include `ProtectedRegionKind.TABLE_OBJECT` in `active_regions`, and filter `active_regions` by temporal overlap when `start_ms`/`end_ms` are provided. Add a symmetric overlap check (`max(inter/b1, inter/b2) >= min_overlap_ratio`) so wide table regions reliably trigger avoidance.
   - Add `caption_layout_to_avoidance_intervals(plan)` + lightweight frame region probe `detect_protected_visual_regions(source, clip_in_ms, clip_out_ms, crop_boxes)` (extracting lower-third `SOURCE_ON_SCREEN_TEXT` pill/banner overlays like `"لەم پۆدکاستەدا:"`, persistent lower `TABLE_OBJECT` occupancy in wide/table shots, and cropped `SPEAKER_FACE` boxes) so `pipeline.py:2410, 4300` builds `face_intervals` via `plan_caption_layout` and passes them into `build_ass`.

## Files and symbols

| File | Symbol | Change |
|---|---|---|
| `src/hawedit/captions.py` | `VIRAL_FONT_SIZE` (`:303`), `VIRAL_THEME` (`:378`), `POPUP_MAX_CHARS` (`:184`) | `128`, `outline=6.0, margin_v=450`, `20` |
| `src/hawedit/shot_plan.py` | `ProtectedRegionKind` (`:45`), `ProtectedContentRegion` (`:57`) | Add `TABLE_OBJECT` and optional `start_ms`/`end_ms` |
| `src/hawedit/caption_layout.py` | `BOTTOM_BAND_BOX` (`:46`), `_boxes_intersect` (`:121`), `plan_caption_layout` (`:140`), new helper `detect_protected_visual_regions` | Time-window filtering, `TABLE_OBJECT`, teaser pill & table detection, avoidance intervals |
| `src/hawedit/pipeline.py` | `:2410`, `:4300` | Wire `plan_caption_layout` + `detect_protected_visual_regions` -> `face_intervals` and `max_popup_width_px=POPUP_MAX_WIDTH_PX` |
| `src/hawedit/assembly.py` | `render_assembled_reel` (`:308`) | Pass `VIRAL_FONT_SIZE`, `VIRAL_THEME`, `POPUP_MAX_CHARS`, `POPUP_MAX_WORDS` |
| `tests/test_captions.py`, `tests/test_caption_layout.py` | `:1395, 1432, 1436`, new AC1–AC4 tests | Update old constants; add EARS pixel & layout tests |
| `tests/golden/*.png` (3 `VIRAL_THEME` goldens) + `tests/test_captions.py:544-550` | — | Re-render with owner `[HAWA]` approval (batched with D6/D7) |
| `DECISIONS.md` | `## D-350` | Document phone-readable sizing, lower-middle safe zone, and protected table/teaser-label avoidance |

## Divergence and ADR

Implements `BLUEPRINT.md` §4.3, §5; no divergence from `BLUEPRINT.md`. Documented in **D-350**.

## Risks and owner actions

1. **Owner approval (`[HAWA]`)**: Replacing the updated golden PNGs under `.codystem-allow-self-edit` (batched once after D6+D7+D5).
2. **Real-media calibration of `TABLE_OBJECT` / teaser heuristic**: Thresholds for static table/banner regions will be validated against the three Zar episodes in `D:\HawEdit-media\` without false-triggering on plain shirts/backgrounds.
3. **VEX binding**: Editing `src/hawedit/**` moves `package_digest(src/hawedit)` (`security/wsl-asr-vex.json`).
