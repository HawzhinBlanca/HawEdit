# Plan — Kurdish Caption Source Word Order & Golden Invariant (Phase B7)

Approved-by: user (auto-approved via review policy)

## 1. Goal

Implement Item B7 of the pro-grade program:
"B7. **Captions in source order.** Today's flagship shows two-word chunks reversed (`مەسعود کاک` for `کاک مەسعود`). Add a golden that asserts every caption chunk's words appear in the same order as the forced-alignment words.
Proof: `test_caption_chunks_preserve_source_word_order` over the whole ep29 transcript."

## 2. Proposed Changes

### 2.1 Test Suite Implementation (`tests/test_captions.py`)
Add `test_caption_chunks_preserve_source_word_order` verifying:
1. **Source Sequence Preservation**:
   - For every multi-word sentence across the ep29 dialogue sequence (including phrases like `"کاتێک پۆڵ برێمەر ویستی پێشمەرگە"`, `"کاک مەسعود"`, `"دروست دەکەین"`), chunking under `chunk_caption_events` preserves the exact chronological word sequence.
2. **Geometric RTL Position Monotonicity**:
   - For every chunk $(w_0, w_1, \dots, w_{k-1})$, `compute_rtl_word_positions` produces strictly decreasing center X coordinates:
     $$X(w_0) > X(w_1) > \dots > X(w_{k-1})$$
   - Placing word 0 on the far right and word $k-1$ on the left.
3. **ASS Verification via `verify_caption_text`**:
   - For `CaptionStyle.VIRAL_POPUP` and `CaptionStyle.RTL_WORD_HIGHLIGHT`, text extraction matches the expected source word sequence.
   - Specifically tests that an inverted sequence (e.g. `["مەسعود", "کاک"]`, `["برێمەر", "پۆڵ"]`) is rejected with `CaptionVerificationError`.
4. **Golden Pixel Render Centroid Invariant**:
   - Renders a frame of `"کاک مەسعود"` onto a canvas via FFmpeg/libass with production complex shaping (`shaping=complex`).
   - Analyzes pixel bounding boxes and centroids, proving that the pixel center of `"کاک"` ($X \approx 620..640$) is strictly to the right of `"مەسعود"` ($X \approx 470..500$), i.e. $X_{c}(\text{"کاک"}) > X_{c}(\text{"مەسعود"})$.
   - Conversely, proves that the legacy `CaptionStyle.WORD_HIGHLIGHT` inline-tag layout produces inverted centroids ($X_{c}(\text{"کاک"}) < X_{c}(\text{"مەسعود"})$), demonstrating why the pro-grade RTL styles are required and proving the bug cannot recur.

### 2.2 Tasks

- **Task 1**: Implement `test_caption_chunks_preserve_source_word_order` in `tests/test_captions.py` covering sequence preservation, geometric monotonicity, caption verification refusal of inversions, and golden pixel centroid assertion.
- **Task 2**: Verify against the canonical gate (`scripts/verify.sh`), ensure zero skips, and record the ledger transition via `scripts/update-ledger.sh`.

## 3. Verification Plan

- Run `pytest tests/test_captions.py -k test_caption_chunks_preserve_source_word_order -v`.
- Run full canonical gate: `bash scripts/verify.sh`.
- Confirm 0 skipped, 0 failed, test count >= 3,732.
