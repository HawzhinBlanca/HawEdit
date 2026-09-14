# Research — Kurdish Caption Source Word Order & Golden Invariant (Phase B7)

## 1. Executive Summary & Problem Context

In Kurdish (Sorani / Arabic script, `ckb`), written text and reading direction strictly proceed Right-to-Left (RTL).
Item B7 of the pro-grade program (`specs/pro-grade-program/gemini-agent-prompt-2026-09-13.md`) specifies:

> **B7. Captions in source order.** Today's flagship shows two-word chunks reversed (`مەسعود کاک` for `کاک مەسعود`). Add a golden that asserts every caption chunk's words appear in the same order as the forced-alignment words.
> Proof: `test_caption_chunks_preserve_source_word_order` over the whole ep29 transcript.

This defect manifested in early flagship outputs where two-word Kurdish phrases such as:
1. `کاک مەسعود` (Kak Masud)
2. `پۆڵ برێمەر` (Paul Bremer)
3. `دروست دەکەین` (drust dakeyn)

were rendered on screen as:
1. `مەسعود کاک`
2. `برێمەر پۆڵ`
3. `دەکەین دروست`

---

## 2. Root Cause Analysis

### 2.1 The Libass Inline Run Splitting Defect
In `libass` (the subtitle renderer used by FFmpeg's `subtitles` and `ass` filters), inline override tags (such as `{\...}`) partition the text string of a Dialogue event into discrete visual runs.
While HarfBuzz connects cursive Arabic glyphs *inside* an uninterrupted run, `libass`'s internal layout engine arranges separate override runs in **Left-to-Right (LTR) order by default** (upstream libass issue #406).

Specifically:
- In `CaptionStyle.WORD_HIGHLIGHT`, `_karaoke()` emits:
  ```ass
  Dialogue: 0,0:00:00.00,0:00:00.90,Kurdish,,0,0,0,,{\kf40}کاک {\kf50}مەسعود
  ```
  Because of the `{\kf50}` tag between the two words, `libass` splits the dialogue line into:
  - Run 0: `{\kf40}کاک `
  - Run 1: `{\kf50}مەسعود`
  `libass` places Run 0 at the **left** edge of the bounding box and Run 1 at the **right** edge.

- Measured on `hawapc01` with FFmpeg 8.1.1 full:
  - Run 0 (`کاک`, active at $t=0.2\text{s}$ in Electric Gold): horizontal pixel bounds $X \in [407, 453]$ (left side).
  - Run 1 (`مەسعود`, inactive in White): horizontal pixel bounds $X \in [454, 673]$ (right side).

- Because native Kurdish reading flows Right-to-Left, a viewer's eyes scan the right side first ($X \in [673, 454]$), reading `مەسعود`, and then the left side ($X \in [453, 407]$), reading `کاک`. The viewer reads: **`مەسعود کاک`**.

### 2.2 The RTL-Safe Solutions
Two caption rendering paradigms in `src/hawedit/captions.py` avoid this defect entirely:

1. **`CaptionStyle.VIRAL_POPUP`**:
   - Emits a single bounce animation tag at the beginning of the dialogue event, with **zero inline tags between words**:
     ```ass
     Dialogue: 0,0:00:00.00,0:00:00.90,Kurdish,,0,0,0,,{\t(0,80,\fscx112\fscy112)\t(80,160,\fscx100\fscy100)}کاک مەسعود
     ```
   - HarfBuzz and FriBidi shape the entire string as a unified RTL text run.
   - Measured pixel positions:
     - `کاک` (first word): $X \in [580, 660]$ (right side).
     - `مەسعود` (second word): $X \in [422, 570]$ (left side).
     - A Kurdish reader reading RTL reads `کاک` first, then `مەسعود`.

2. **`CaptionStyle.RTL_WORD_HIGHLIGHT`**:
   - Pre-computes exact horizontal center coordinates using `compute_rtl_word_positions` via HarfBuzz metrics:
     $$X_{center} = \text{round}\left(\frac{\text{canvas\_width} + W_{full}}{2} - W_{prefix} + \frac{W_{word}}{2}\right)$$
   - Guaranteed mathematical invariant:
     $$X(w_0) > X(w_1) > \dots > X(w_{n-1})$$
   - Measured center positions for `("کاک", "مەسعود")`:
     - $X(\text{"کاک"}) = 638\text{ px}$ (right side).
     - $X(\text{"مەسعود"}) = 488\text{ px}$ (left side).
     - $638 > 488$.
   - Each word is placed via an explicit `\pos(x, y)` dialogue event, ensuring zero inline tag interference.

---

## 3. Acceptance Criteria (EARS Format)

- **AC-B7.1 (Source Order Invariant):**
  WHEN any multi-word sentence is partitioned into caption chunks via `chunk_caption_events`,
  THE words in each chunk SHALL strictly match the index and chronological order of the forced-alignment source words.

- **AC-B7.2 (Geometric RTL Invariant):**
  WHEN `compute_rtl_word_positions` calculates layout positions for any sequence of Kurdish words $(w_0, w_1, \dots, w_{n-1})$,
  THE computed center X coordinates SHALL be strictly monotonic decreasing ($X(w_0) > X(w_1) > \dots > X(w_{n-1})$).

- **AC-B7.3 (Text Parsing & Verification):**
  WHEN `verify_caption_text` validates ASS subtitles generated under `CaptionStyle.VIRAL_POPUP` or `CaptionStyle.RTL_WORD_HIGHLIGHT`,
  THE recovered tokens SHALL match the source word sequence, and any inverted text (e.g. `["مەسعود", "کاک"]`) SHALL raise `CaptionVerificationError`.

- **AC-B7.4 (Golden Render Centroid Invariant):**
  WHEN a two-word Kurdish chunk (e.g. `"کاک مەسعود"`, `"پۆڵ برێمەر"`) is rendered onto video frames under production caption styling,
  THE horizontal pixel centroid of the first word $w_0$ SHALL be strictly greater than the centroid of the second word $w_1$ ($X_{c}(w_0) > X_{c}(w_1)$).

- **AC-B7.5 (Full Transcript Coverage):**
  WHEN `test_caption_chunks_preserve_source_word_order` runs over the ep29 dialogue sentence sequence,
  EVERY caption chunk SHALL be verified to preserve source word order with zero inversions across both text and geometric layout.
