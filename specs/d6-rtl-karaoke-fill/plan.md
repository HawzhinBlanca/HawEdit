# Plan — Right-to-left intra-word karaoke fill (D6 / d6-rtl-karaoke-fill)

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"

Read `research.md` and `spec.md` first. Captures and probe script: `captures/strip_*.png`, `captures/probe_d6.py.txt`.

## Approach

Replace libass `\kf` (which sweeps left-to-right inside Sorani words per libass #406) in `CaptionStyle.WORD_HIGHLIGHT` with a two-layer animated `\clip` highlight driven by a single-pass `libass` pixel-box probe:

1. **Single-pass word-box probe (`_measure_word_boxes`)** in `src/hawedit/captions.py`:
   - Assigns each word in an event's rendered visual lines a distinct RGB colour (`\1c`), renders one `rgb24` frame with `bord=0, shad=0` through `subtitle_filter` (exact same `font_name`, `font_size`, `alignment`, `margin_v`, `play_res_x`, `play_res_y`, `\N` breaks, `RTL_MARK`, and `EMPHASIS_SCALE` if present), and extracts each word's exact pixel bounding box `(x0, y0, x1, y1)`.
   - Bounded LRU/process cache keyed by the complete measurement context (reusing `_measurement_context`) so identical lines or re-renders hit memory. Fails closed with `CaptionVerificationError` if `find_ffmpeg()` is `None` or rendering fails (strict fail-stop; never falls back to `\kf`).
2. **Two-layer animated `\clip` emission in `build_ass`**:
   - Style header adds highlight style variants (`KurdishHighlight`, `KurdishTopHighlight`) with `PrimaryColour = theme.primary` and matching outline/shadow (`Outline = theme.outline, Shadow = theme.shadow` when `border_style == 1`, or `border_style = 1, outline = 0, shadow = 0` when `is_plate=True` so semi-transparent plates on Layer 0 do not double-darken), while base `Kurdish`/`KurdishTop`/`KurdishPlate`/`KurdishTopPlate` in `WORD_HIGHLIGHT` use `PrimaryColour = theme.secondary` for unspoken colour.
   - Layer 0 emits the complete unbroken line/chunk from `ev_start` to `ev_end`.
   - Layer 1 emits one event per word `[word.start_ms, ev_end]` immediately after its Layer 0 event (preserving consecutive-line grouping for `verify_caption_text` deduplication), animated via:
     - RTL words (Arabic-script codepoints): `{\clip(x_r,y_t,x_r,y_b)\t(0,dur,\clip(x_l,y_t,x_r,y_b))}` (right-to-left sweep).
     - LTR words (Latin/digits): `{\clip(x_l,y_t,x_l,y_b)\t(0,dur,\clip(x_l,y_t,x_r,y_b))}` (left-to-right sweep).
   - Remove `_karaoke` (`\kf` builder) or replace its callers so no `WORD_HIGHLIGHT` path emits `\kf`.

## Files and symbols

| File | Symbol | Change |
|---|---|---|
| `src/hawedit/captions.py` | `_measure_word_boxes` (new helper) | Single-pass `rgb24` libass per-word bounding boxes with context cache |
| `src/hawedit/captions.py` | `_karaoke` (`:1469`), `build_ass` (`:1557-2204`) | Emit Layer 0 base + Layer 1 animated `\clip` events for `WORD_HIGHLIGHT`; add `KurdishHighlight`/`KurdishTopHighlight` style rows |
| `tests/test_captions.py` | `:411`, `:1352`, `:1359`, new AC1/AC3/AC4/AC5/AC6 pixel tests | Update `\kf`/Layer-0 event assertions; add intra-word RTL sweep pixel assertions |
| `tests/test_audit_regressions.py` | `:208` (`test_karaoke_timings_cover_the_silence_between_words`) | Assert Layer 1 word-2 start time reflects the 1 s gap (`0:00:01.50`) |
| `tests/test_caption_context.py` | `:40, 80` | Count Layer 0 base `Dialogue: 0,` events for wrapping/chunking checks |
| `tests/test_render_caption_revision.py` | `:336` (`test_the_revised_ass_actually_changes_style`) | Assert `KurdishHighlight` / `\clip(` present in `word_highlight` and absent in `line` |
| `tests/golden/kurdish-caption-fixture.png` + `tests/test_captions.py:548` | — | Re-render and re-pin SHA-256 **only with owner `[HAWA]` approval** |
| `DECISIONS.md` | `## D-348` | Document replacement of `\kf` with two-layer `\clip` RTL sweep (supersedes D-269 `\kf` retention) |

## Divergence and ADR

Implements `BLUEPRINT.md` §4.3 and §4.3.6; no divergence from `BLUEPRINT.md`. Supersedes D-269's remaining `\kf` clause via **D-348**.

## Risks and owner actions

1. **Owner approval (`[HAWA]`)**: Replacing `tests/golden/kurdish-caption-fixture.png` (and updating `GOLDEN_DIGESTS`) under `.codystem-allow-self-edit`, because at `t = 0.500 s` the highlight sweeps right-to-left (`ڕۆژنامەوا` gold, `نی` white) instead of left-to-right.
2. **VEX source digest**: Changing `src/hawedit/captions.py` changes `package_digest(src/hawedit)`, requiring lead/owner re-pin of `security/wsl-asr-vex.json` on integration.
3. **Host/CI ffmpeg requirement**: `WORD_HIGHLIGHT` now requires `find_ffmpeg()` just like `RTL_WORD_HIGHLIGHT` and `KINETIC_POP`.
