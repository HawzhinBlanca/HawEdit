# Research — Keyword Emphasis & Multi-Color Kinetic Subtitles

## 1. Problem Statement & Motivation
In short-form social video production (TikTok, Instagram Reels, YouTube Shorts), visual pacing and retention are heavily driven by subtitle dynamics. Tools like OpusClip, Submagic, and Captions.ai establish high retention by highlighting key emotional and semantic words in contrasting accent colors rather than using a single uniform color.

In HawEdit:
1. `CaptionStyle.VIRAL_POPUP` currently renders all popups in uniform Electric Gold (`&H0000E5FF`).
2. `CaptionStyle.RTL_WORD_HIGHLIGHT` currently highlights all active words in Electric Gold and inactive words in Dim White (`&H00FFFFFF`).
3. Viewers watching Kurdish dialogue (e.g. Zar Podcast Episode 29) miss semantic emphasis cues when high-stakes proper names (like *"پۆڵ برێمەر"*, *"پێشمەرگە"*, *"عێراق"*), numbers/quantities (*"ملیۆن"*, *"هەزار"*, *"دوو"*), or dramatic contrast/negation words (*"هەرگیز"*, *"مەحاڵە"*, *"کارەسات"*) look visually identical to common function words (*"لە"*, *"کە"*, *"بۆ"*).

## 2. Invariants & Constraints

### 2.1 The `libass` RTL Layout Invariant (ADR D-269)
As established in ADR D-269, inserting inline override tags (`\c`, `\kf`, etc.) inside a multi-word text string partitions text into separate layout runs that `libass` renders in **Left-to-Right** order (libass issue #406).
- **Rule 1**: In `CaptionStyle.VIRAL_POPUP` with multiple words, we must **NEVER** insert inline `\c` tags between words in a single Dialogue event.
- **Rule 2**: Instead, in `VIRAL_POPUP`, when a popup chunk contains an emphasis word, the entire popup event receives the appropriate category Style (e.g., `KurdishCyan`, `KurdishCoral`, `KurdishEmerald`). When `max_words_per_event=1` (1-word popups), every word is its own event and receives individual styling with zero run splits.
- **Rule 3**: In `CaptionStyle.RTL_WORD_HIGHLIGHT`, every word is *already* rendered as an independent Dialogue event positioned with exact `\pos(x, y)` coordinates. Therefore, the active word can directly specify its exact category Style without any inline color tags or layout risk!

### 2.2 Text Integrity Invariant (Kurdish Invariant #1)
The transcript text displayed on screen must remain the raw surface form spoken by the participant. Emphasis classification operates on normalized forms for matching, but the rendered glyphs are always the original words.

### 2.3 Strict Fail-Stop Invariant
If font files lack required glyphs or if style generation encounters unexpected states, the pipeline must raise immediately rather than falling back silently.

## 3. Kurdish Emphasis Taxonomy & Color Palette

We define four visual categories in ASS BGR format (`&HAABBGGRR`):

| Category | Semantic Function | Target Color (Hex / RGB) | ASS BGR Value | Examples |
|---|---|---|---|---|
| **`DEFAULT`** | Standard active spoken word | Electric Gold (`#FFE500`) | `&H0000E5FF` | Default speech words |
| **`ENTITY`** | Proper nouns, places, institutions | Electric Cyan (`#00FFFF`) | `&H00FFFF00` | پۆڵ برێمەر, پێشمەرگە, عێراق, کوردستان, بەغدا |
| **`ACTION_ALERT`** | Negation, shock, danger, contrast | Vivid Coral (`#FF3B30`) | `&H00303BFF` | هەرگیز, نەخێر, کارەسات, مەترسی, مەحاڵە, بەڵام |
| **`NUMERIC`** | Digits, quantities, amounts, dates | Neon Emerald (`#00FF66`) | `&H0066FF00` | هەزار, ملیۆن, ٠-٩, ١٠٠, هەموو, زۆرترین |

## 4. Code Architecture & Affected Modules

1. **`src/hawedit/captions.py`**:
   - Introduce `EmphasisCategory(Enum)`: `DEFAULT`, `ENTITY`, `ACTION_ALERT`, `NUMERIC`.
   - Introduce `classify_kurdish_emphasis(token: str) -> EmphasisCategory`: Fast regex + normalized keyword dictionary matching.
   - Define V4+ style variants for each category in `build_ass`:
     - Bottom: `Kurdish` (Gold), `KurdishCyan`, `KurdishCoral`, `KurdishEmerald`.
     - Bottom Plate: `KurdishPlate`, `KurdishCyanPlate`, `KurdishCoralPlate`, `KurdishEmeraldPlate`.
     - Top (Face collision): `KurdishTop`, `KurdishTopCyan`, `KurdishTopCoral`, `KurdishTopEmerald` (and plate variants).
   - In `VIRAL_POPUP` event generation:
     - Check chunk words for emphasis category.
     - Select corresponding active style.
   - In `RTL_WORD_HIGHLIGHT` event generation:
     - When `j == active_idx`, choose style based on `classify_kurdish_emphasis(word.w)`.
   - Add parameter `keyword_emphasis: bool = True` to `build_ass`.

2. **`src/hawedit/pipeline.py`**:
   - Expose `--keyword-emphasis / --no-keyword-emphasis` CLI flags (default: enabled).
   - Pass `keyword_emphasis` to `build_ass`.

3. **`src/hawedit/editor_agent.py`**:
   - Include `keyword_emphasis: bool` in `EditorAgent` parameter model.

## 5. Risk Assessment & Verification Strategy
- **Risk**: Does adding styles break existing tests that assert specific ASS styles?
  - **Mitigation**: Existing styles (`Kurdish`, `KurdishDim`, `KurdishPlate`, etc.) remain identical. New styles are appended to the V4+ header.
- **Risk**: Font glyph coverage for colored text.
  - **Mitigation**: All styles use the same verified font (`Noto Naskh Arabic`), only changing `PrimaryColour`.
- **Verification**:
  - Unit tests for `classify_kurdish_emphasis` on Kurdish words, numbers, entities, and neutral words.
  - ASS generation tests asserting valid header styles and correct category selection in `VIRAL_POPUP` and `RTL_WORD_HIGHLIGHT`.
  - Full gate pass (`scripts/verify.sh` exiting 0).
