# Plan — Kurdish RTL Word Highlight & Viral Popups (Task T2.14)

## Status
Approved-by: User Review Policy (/goal make canon)

## Goal
Eliminate the Left-to-Right layout reversal and sweep defects in Kurdish subtitles, and deliver industry-leading viral captioning:
1. **`CaptionStyle.VIRAL_POPUP`**: High-retention 1-to-2 word popups with micro-bounce scaling, Electric Gold highlight, and 100% pure Kurdish text (zero inline tag splitting).
2. **`CaptionStyle.WORD_HIGHLIGHT` (RTL-Safe)**: Ensure multi-word lines maintain correct Right-to-Left visual order ($X_{w1} > X_{w2} > X_{w3}$) and highlight sequentially Right-to-Left without `libass` run reversal.
3. **Pipeline Integration**: Expose `--caption-style {line, word_highlight, viral_popup}` in `pipeline.py`, defaulting to `viral_popup` when `--brand-kit` or social content type is active.
4. **ADR D-269**: Formalize Kurdish RTL subtitle shaping and kinetic positioning in `DECISIONS.md`.

---

## Proposed Tasks

### Task 1: RTL-Aware Subtitle Generator & Viral Popups in `src/hawedit/captions.py`
1. Add `CaptionStyle.VIRAL_POPUP = "viral_popup"` to `CaptionStyle`.
2. Introduce `_build_viral_popup_events` for 1-to-2 word popups with elastic bounce tag `{\t(0,80,\fscx112\fscy112)\t(80,160,\fscx100\fscy100)}` and Electric Gold styling.
3. Introduce `_build_rtl_word_highlight_events` using advance widths from `measure_rendered_caption_width` to render multi-word phrases with correct RTL word order and RTL highlight progression.
4. Update `build_ass` to support `CaptionStyle.VIRAL_POPUP` and the upgraded `CaptionStyle.WORD_HIGHLIGHT`.

### Task 2: Tests in `tests/test_captions.py`
1. Unit tests for `CaptionStyle.VIRAL_POPUP` event generation.
2. Assertion that rendered ASS text for Kurdish sentences contains words in strictly Right-to-Left visual order.
3. Pixel test verifying that the first spoken word is rendered on the right side of the canvas.

### Task 3: Pipeline & CLI Wiring in `src/hawedit/pipeline.py`
1. Add `--caption-style {line,word_highlight,viral_popup}` CLI argument.
2. Connect to `build_ass` in `render_clip_candidates` and `PipelineRun`.

### Task 4: ADR D-269 in `DECISIONS.md`
1. Record `## D-269 · Kurdish RTL subtitle word-by-word highlighting and kinetic popups`.

### Task 5: Gate Verification & Test Floor Ratchet
1. Run `bash scripts/verify.sh` to ensure green gate.
2. Ratchet test floor in `scripts/test-count.floor` and update `specs/rtl-word-highlight/ledger.log`.
