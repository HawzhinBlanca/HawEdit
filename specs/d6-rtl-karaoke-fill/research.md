# Research — Right-to-left intra-word karaoke fill (D6 / d6-rtl-karaoke-fill)

**Provenance.** 2026-11-18, branch `gemini/lane-4` at commit `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf`. Host `HawaPC01`, Windows 11 (`Windows-11-10.0.26300-SP0`), `.venv` CPython `3.12.10`, OpenCV `4.12.0`, `ffmpeg 8.1.1-full_build-www.gyan.dev` (`--enable-libass`, `--enable-libharfbuzz`, `--enable-libfribidi`), font `assets/fonts/NotoNaskhArabic-Regular.ttf` (`sha256:2f4b88e6ee50fa82c617e2d1d4ba18281cb1c6cd71c3af3ec64970c23995db4b`). Serena MCP was unavailable in this session, so all symbol callers were mapped with `rg` over `src/` and `tests/`. Diagnostic script and rendered frame strips: `specs/d6-rtl-karaoke-fill/captures/probe_d6.py.txt` and `strip_*.png`.

## Defect (measured on rendered frames)

`DEFAULT_CONTENT_TYPE` (`PODCAST`) and the `INTERVIEW` and `SOCIAL` profiles default to `CaptionStyle.WORD_HIGHLIGHT` (`src/hawedit/content_type.py:61,70,88`). `build_ass` delegates `WORD_HIGHLIGHT` to `_karaoke` (`src/hawedit/captions.py:1469-1493, 1830-1833`), which emits inline `{\kf<cs>}` tags.

D-334 (`ASS_ENCODING_AUTO = -1` + leading `RTL_MARK` U+200F) fixed *word* order so the first word sits rightmost and words activate in reading order. However, `libass` issue #406 remains unfixed in `libass`: `\kf` sweeps the fill boundary from $X_{\min}$ to $X_{\max}$ (left-to-right) inside each Sorani word, lighting up the **end** of each word (`انی`, `ێر.`) before its **beginning** (`ڕۆژ`, `هە`). This is visible directly in `tests/golden/kurdish-caption-fixture.png` at `t = 0.500 s`.

Measured on `GOLDEN_CAPTION_TEXT` (`"ڕۆژنامەوانی کوردی لە هەولێر."`, `VIRAL_THEME`, 108 pt; word 0 `"ڕۆژنامەوانی"` occupies `x = [581, 898]`):

| Renderer / variant | Sample time | Active word | Gold X range & mean | White X range & mean | Intra-word sweep direction |
|---|---|---|---|---|---|
| Baseline `\kf` (`baseline_kf`) | `0.15 s` | `ڕۆژنامەوانی` (0–0.6 s) | `581..661`, mean `627.1` | `668..896`, mean `788.9` | **LTR (wrong)** |
| Baseline `\kf` (`baseline_kf`) | `0.30 s` | `ڕۆژنامەوانی` (0–0.6 s) | `581..751`, mean `667.9` | `753..896`, mean `829.2` | **LTR (wrong)** |
| Baseline `\kf` (`baseline_kf`) | `0.45 s` | `ڕۆژنامەوانی` (0–0.6 s) | `581..817`, mean `699.3` | `818..896`, mean `856.5` | **LTR (wrong)** |
| Baseline `\kf` (`baseline_kf`) | `1.50 s` | `هەولێر.` (1.2–1.8 s) | `184..271`, mean `233.2` | `272..343`, mean `309.7` | **LTR (wrong)** |
| Candidate `\clip` (`clip_bord4`) | `0.15 s` | `ڕۆژنامەوانی` (0–0.6 s) | `816..896`, mean `855.6` | `581..815`, mean `699.0` | **RTL (correct)** |
| Candidate `\clip` (`clip_bord4`) | `0.30 s` | `ڕۆژنامەوانی` (0–0.6 s) | `728..896`, mean `820.5` | `581..727`, mean `658.8` | **RTL (correct)** |
| Candidate `\clip` (`clip_bord4`) | `0.45 s` | `ڕۆژنامەوانی` (0–0.6 s) | `668..896`, mean `788.4` | `581..661`, mean `627.2` | **RTL (correct)** |
| Candidate `\clip` (`clip_bord4`) | `0.80 s` | `کوردی` (0.6–1.0 s) | `492..560`, mean `528.3` | `421..489`, mean `451.3` | **RTL (correct)** |
| Candidate `\clip` (`clip_bord4`) | `1.50 s` | `هەولێر.` (1.2–1.8 s) | `258..343`, mean `303.3` | `184..252`, mean `226.5` | **RTL (correct)** |

## Candidate comparison (tested on rendered frames)

1. **Candidate 1 (selected): Two-layer animated `\clip` sweep (`strip_clip_bord4.png`, `strip_mixed_clip.png`)**
   - **Layer 0** (`Kurdish` / `KurdishTop` / `KurdishPlate` / `KurdishTopPlate`, `PrimaryColour = theme.secondary`): renders the unbroken line in unspoken white for `[event_start, event_end]`.
   - **Layer 1** (`KurdishHighlight` / `KurdishTopHighlight`, `PrimaryColour = theme.primary`, matching `Outline` and `Shadow` when `border_style == 1`, or `border_style = 1, outline = 0, shadow = 0` over a `border_style == 3` plate so semi-transparent plates do not double-darken): renders one Dialogue event per word from `w.start_ms` to `event_end` with identical text, animated via `\clip`:
     - RTL words (containing Arabic-script codepoints): `{\clip(x_r,y_t,x_r,y_b)\t(0,dur,\clip(x_l,y_t,x_r,y_b))}` — sweeps smoothly **right-to-left**.
     - LTR words (Latin/digits): `{\clip(x_l,y_t,x_l,y_b)\t(0,dur,\clip(x_l,y_t,x_r,y_b))}` — sweeps **left-to-right** inside the Latin word while keeping RTL word ordering across the line.
   - **Outline & compositing check (`t = 1.90 s` vs single-layer all-gold render)**:
     - Layer 1 with `\bord0\shad0` (`clip_bord0`): `max_diff = 65`, `3,456` anti-aliased fringe pixels differed around outlines.
     - Layer 1 with matching `Outline = 4, Shadow = 2` (`clip_bord4`): `max_diff = 0`, `0` differing pixels.
   - **Mixed-script check (`"OpusClip زۆر باشە."`)**: `"OpusClip"` swept LTR (`mean_x: 494.5 -> 545.8 -> 586.3`), `"زۆر"` swept RTL (`398.8 > 365.4`), `"باشە."` swept RTL (`298.8 > 245.1`).
   - **Word bounding-box measurement (`rgb24` single-pass colour probe)**: assigns distinct RGB fills per word (`bord=0, shad=0`) on `format=rgb24` in one `ffmpeg` call (`~130 ms` uncached for one probe; cached by `(text, font, size, canvas, alignment, margin_v)`). Compared against plain tag-free render: `8,688` vs `8,682` pixels (`6 px` AA difference, zero glyph shift). Handles single-line, multi-line (`\N`), `\fscx118` emphasis, and mixed BiDi runs (where `compute_rtl_word_positions` fails).
   - **`verify_caption_integrity(..., expected_text=...)`**: already passes via consecutive-line deduplication (`_collapse` / `deduped_lines` in `captions.py:2495-2508`).

2. **Candidate 2 (rejected): Single-line inline `\t(t, t+1, \1c...)` (`strip_per_word_inline.png`)**
   - Failed in `libass`: putting `\t(...,\1c...)` inside the line coloured the entire line gold at `t = 0.15 s` (`white_px = 0` across all timestamps) and does not provide an intra-word sweep.

3. **Candidate 3 (already exists as `RTL_WORD_HIGHLIGHT`, not sufficient alone)**:
   - `RTL_WORD_HIGHLIGHT` emits discrete per-word `\pos` events with no intra-word sweep and assumes strictly monotonic LTR-free word widths (`compute_rtl_word_positions`), which breaks on mixed Latin+Sorani and `\N`-wrapped lines.

## Symbols and references

- Production code: `src/hawedit/captions.py` (`_karaoke` `:1469`, `build_ass` `:1557-2204`, `_mark_right_to_left` `:2206`, `CaptionTheme.style_row` `:230`), `src/hawedit/content_type.py:61,70,88`, `src/hawedit/pipeline.py:2410, 4300`, `src/hawedit/assembly.py:308`, `src/hawedit/proposals.py:596, 767, 949`.
- Golden tests & references: `tests/golden/kurdish-caption-fixture.png` (digests pinned at `tests/test_captions.py:542-551`).
- Blueprint / ADR refs: `BLUEPRINT.md` §4.3, §4.3.6; `DECISIONS.md` D-269 (`:13864`), D-334 (`:16548`).

## Risks

- **Golden image change**: `tests/golden/kurdish-caption-fixture.png` renders `WORD_HIGHLIGHT` at `t = 0.500 s` (currently showing `"وانی"` gold on the left and `"ڕۆژنامە"` white on the right). Replacing it requires explicit owner approval (`[HAWA]`).
- **Renderer dependency at `build_ass(..., style=WORD_HIGHLIGHT)` time**: Measuring word bounding boxes invokes `ffmpeg` (same requirement as `RTL_WORD_HIGHLIGHT`, `KINETIC_POP`, and `max_width_px` wrapping). If `find_ffmpeg()` is `None`, `CaptionVerificationError` is raised (strict fail-stop; never falls back to buggy `\kf`).
- **CI Linux `ffmpeg` (zackees v8.0)**: Animated `\t(\clip(...))` behaviour on Linux `libass` will be verified by the pixel tests and golden comparison in CI.
- **VEX binding (`security/wsl-asr-vex.json`)**: Editing `src/hawedit/captions.py` moves `package_digest(src/hawedit)`, requiring lead/owner VEX re-pin before the full gate turns green.
