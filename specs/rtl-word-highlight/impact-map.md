# Impact Map — RTL Word Highlight & Viral Popups (Task T2.14)

## Modified Symbols

### `src/hawedit/captions.py`
- `CaptionStyle`: Enum gaining `VIRAL_POPUP = "viral_popup"`.
  - Impact: Backward compatible; existing `.LINE` and `.WORD_HIGHLIGHT` remain valid enum values.
- `_karaoke`: Modified to support RTL layout or replaced/supplemented by `_build_rtl_word_highlight_events` and `_build_viral_popup_events`.
- `build_ass`: Extended to handle `CaptionStyle.VIRAL_POPUP`.

### `src/hawedit/pipeline.py`
- CLI parser: `--caption-style` argument added with choices `line`, `word_highlight`, `viral_popup`.
- `render_clip_candidates`: Passes selected caption style to `build_ass`.

---

## Callers and Verification

| Caller File | Function / Scope | Risk | Mitigation |
| :--- | :--- | :--- | :--- |
| `src/hawedit/pipeline.py` | `run_pipeline`, `render_clip_candidates` | Low | Defaults to existing behavior unless overridden or social profile active |
| `src/hawedit/render.py` | `render_clip` | None | Operates on pre-generated ASS file path |
| `src/hawedit/assembly.py` | `render_assembled_reel` | Low | Calls `build_ass` with default or passed style |
| `tests/test_captions.py` | Test suite | High | Existing tests for `CaptionStyle.WORD_HIGHLIGHT` must continue to pass |
| `tests/test_pipeline.py` | Pipeline CLI tests | Medium | Verify argument parsing and default propagation |
