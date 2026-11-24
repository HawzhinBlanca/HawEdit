# Research — Phone-readable captions off faces, tables, and burned-in teaser label (D5 / d5-phone-readable-captions)

**Provenance.** 2026-11-18, branch `gemini/lane-4` at commit `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf`. Host `HawaPC01`, Windows 11 (`Windows-11-10.0.26300-SP0`), `.venv` CPython `3.12.10`, OpenCV `4.12.0`, `ffmpeg 8.1.1-full_build-www.gyan.dev`. Real Zar Podcast media (read-only): `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4` (`sha256:6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0`) and `D:\HawEdit-media\sources\zar-mjewr-cooking-with-hawzhin-2026-10-26__k_jxP903t5w.mp4` (`sha256:b594c941d7a95dbf68b6eee9fb103c14bead4593ef9ed3cf7ae3ee848221b273`). Serena MCP was unavailable in this session; callers mapped with `rg`. Probe script and captures: `specs/d5-phone-readable-captions/captures/probe_d5.py.txt`, `grid_d5_sizes.jpg`, `teaser_and_table_boxes.jpg`.

## Findings on current codebase & real Zar Podcast 9:16 frames

1. **Size, outline, grouping, and safe zone gaps (`captions.py`, `pipeline.py`, `assembly.py`, `proposals.py`):**
   - `build_ass()` defaults (`captions.py:1559-1567`) remain `font_size = 64`, `theme = REPORT_THEME` (`bold=False, outline=3.0, margin_v=140`), `max_words_per_event = None` (entire sentence in one block). `assembly.py:308` (`render_assembled_reel`) and `proposals.py:596, 767, 949` invoke `build_ass()` with these defaults, burning tiny 64 pt full-sentence captions at `y_center = 1748 px` inside TikTok/Reels/Shorts bottom UI bars.
   - `pipeline.py:2410-2445, 4300-4331` overrides to `VIRAL_FONT_SIZE = 108`, `VIRAL_THEME` (`outline=4.0, margin_v=360`), `max_chars_per_line = POPUP_MAX_CHARS (22)`, `max_words_per_event = POPUP_MAX_WORDS (3)`, **without** passing `max_popup_width_px` (`None`) and with `22 > 20` chars violating `sanity_gate.py:140`.
   - Measured ink heights on `1080x1920` over real frame `excerpt_05s_9x16` (`"ژیری دەستکرد داهاتووە."`):

| Config | Font | Size | Outline | MarginV | Measured ink height | Ink width | Vertical center (`y`) |
|---|---|---|---|---|---|---|---|
| `current_64_out3_mv140` (`REPORT_THEME`) | `Noto Naskh Arabic` | 64 pt | 3.0 | 140 | **35 px** | 316 px | 1748 px (in platform UI) |
| `viral_108_out4_mv360` (`VIRAL_THEME`) | `Noto Naskh Arabic` | 108 pt | 4.0 | 360 | **59 px** | 535 px | 1506 px (clips top of teaser pill) |
| `vazir_120_out6_mv420` | `Vazirmatn` | 120 pt | 6.0 | 420 | **67 px** | 658 px | 1440 px |
| `vazir_128_out6_mv450` (selected) | `Vazirmatn` | 128 pt | 6.0 | 450 | **72 px** (`2.06×` of 64 pt) | 702 px | 1405 px (lower-middle safe zone) |

2. **Protected visual regions on real Zar Podcast 9:16 crops (`teaser_and_table_boxes.jpg`):**
   - **Burned-in `"لەم پۆدکاستەدا:"` teaser pill** (`cooking_teaser_05s_9x16`): measured dark-blue banner at `x = 68..1013`, `y = 1525..1734` (`0.794..0.903` of 1920 px height). `VIRAL_THEME` at `margin_v = 360` (`y_center = 1506`) collides with the pill's top border; `margin_v = 450` (`y_center = 1405`) sits cleanly above it, and if a teaser pill / lower-third nameplate extends into the active caption band (`SOURCE_ON_SCREEN_TEXT`), captions must relocate to `TOP`.
   - **Table / studio foreground objects** (`excerpt_35s_9x16`, `excerpt_110s_9x16`): wide two-shot center crop places the patterned table runner, laptops, and hands across `y = 1060..1920` (`0.55..1.00`), while `y = 0..900` is clear studio curtain. `ProtectedRegionKind` (`shot_plan.py:45-53`) currently lists `SPEAKER_FACE`, `LISTENER_FACE`, `DEMONSTRATION`, `GRAPHIC_OR_CHART`, `LOWER_THIRD_CAPTIONS`, `SOURCE_ON_SCREEN_TEXT`, **lacking `TABLE_OBJECT`**.
   - **Caption layout never wired & lacks temporal intervals**: `caption_layout.py:140` (`plan_caption_layout`) has **zero callers** in `pipeline.py`. Moreover, `ProtectedContentRegion` (`shot_plan.py:57`) lacks optional `(start_ms, end_ms)` temporal bounds, so `caption_layout.py:191` applies every protected region to every cue across the entire clip instead of only overlapping cues, and `pipeline.py:2410, 4300` never passes `face_intervals` or `plate_intervals` to `build_ass`.

## Design choices

1. Upgrade `VIRAL_FONT_SIZE` to `128`, `VIRAL_THEME` to `outline=6.0, shadow=2.0, margin_v=450` (lower-middle safe zone, clear of bottom phone UI and teaser bar), and `POPUP_MAX_CHARS = 20` (matching `sanity_gate.py:140`), passing `max_popup_width_px = POPUP_MAX_WIDTH_PX` (`700`) and `POPUP_MAX_WORDS = 3` in `pipeline.py` and `assembly.py`.
2. Add `ProtectedRegionKind.TABLE_OBJECT` (`shot_plan.py:45`) and optional `start_ms: int | None = None, end_ms: int | None = None` on `ProtectedContentRegion`, filtering `active_regions` per cue time window in `plan_caption_layout` and adjusting `BOTTOM_BAND_BOX` to `(0.05, 0.70, 0.95, 0.80)`.
3. Add a deterministic protected-region extractor (from tracked face boxes + persistent lower-frame blue/high-saturation overlay pill detection for `"لەم پۆدکاستەدا:"` / lower-thirds + persistent lower-band foreground/table-object occupancy) and convert non-`BOTTOM` cues from `plan_caption_layout` into `face_intervals` (and `TOP`/`MID_UPPER` placements) passed to `build_ass` in `pipeline.py`.

## Risks

- **Golden image change**: Updating `VIRAL_FONT_SIZE` (`108 -> 128`) and `VIRAL_THEME` (`outline 4 -> 6, margin_v 360 -> 450`) changes `kurdish-viral-karaoke.png`, `kurdish-hook-card.png`, and `kurdish-caption-fixture.png` (requires `[HAWA]` approval, batched with D6/D7).
- **Existing unit test literals**: `tests/test_captions.py:1395` (`VIRAL_THEME.margin_v == 360`), `:1432` (`VIRAL_FONT_SIZE == 108`), and `:1436` (`POPUP_MAX_CHARS`) pin the previous constants and must be updated cleanly with the plan.
- **VEX binding**: Editing `src/` moves `package_digest(src/hawedit)` (`security/wsl-asr-vex.json`).
