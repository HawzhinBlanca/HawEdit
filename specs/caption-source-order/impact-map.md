# Impact Map — Kurdish Caption Source Word Order (Phase B7)

## 1. Primary Components Under Test & Adjustment

| File | Symbol / Area | Nature of Change | Callers Affected |
|---|---|---|---|
| `tests/test_captions.py` | `test_caption_chunks_preserve_source_word_order` | New comprehensive test suite function implementing B7 golden invariant | Test suite only |
| `src/hawedit/captions.py` | `compute_rtl_word_positions`, `verify_caption_text`, `build_ass` | Verified contract adherence for RTL word placement and word sequence preservation | `render.py`, `pipeline.py`, `web.py` |

---

## 2. Caller Graph & Regression Protection

1. **`compute_rtl_word_positions`**:
   - Callers:
     - `src/hawedit/captions.py:1951` in `build_ass` for `CaptionStyle.RTL_WORD_HIGHLIGHT`.
     - `tests/test_captions.py:2003` in `test_kurdish_two_word_chunk_preserves_source_rtl_order`.
   - Invariant:
     $X(w_0) > X(w_1) > \dots > X(w_{n-1})$ must hold for any sequence of non-empty words.

2. **`verify_caption_text`**:
   - Callers:
     - `tests/test_captions.py` (multiple unit and golden tests).
     - Delivery reconciliation and QC pipeline stages.
   - Invariant:
     Normalizes and compares recovered tokens against expected source word sequence, raising `CaptionVerificationError` on any discrepancy or inversion.

3. **Existing Golden Renders**:
   - `GOLDEN` (`kurdish-caption.png`)
   - `GOLDEN_VIRAL_KARAOKE` (`kurdish-viral-karaoke.png`)
   - `GOLDEN_HOOK_CARD` (`kurdish-hook-card.png`)
   - `GOLDEN_CAPTION_FIXTURE` (`kurdish-caption-fixture.png`)
   - Invariant: Zero modification to existing golden image files or their pinned digests in `GOLDEN_DIGESTS`.
