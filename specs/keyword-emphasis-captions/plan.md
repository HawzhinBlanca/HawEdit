# Implementation Plan — Keyword Emphasis & Multi-Color Kinetic Subtitles

## Approved-by: Wareen (auto-approved)

## Objective
Implement dynamic semantic keyword emphasis for Kurdish subtitles in `CaptionStyle.VIRAL_POPUP` and `CaptionStyle.RTL_WORD_HIGHLIGHT` to boost viewer retention without violating `libass` RTL layout rules (ADR D-269).

## EARS Requirements
1. **WHEN** a subtitle event contains a Kurdish numeral or quantity word, **THE** subtitle engine **SHALL** render that event with Neon Emerald (`&H0066FF00`) highlighting.
2. **WHEN** a subtitle event contains a high-stakes entity or proper noun, **THE** subtitle engine **SHALL** render that event with Electric Cyan (`&H00FFFF00`) highlighting.
3. **WHEN** a subtitle event contains a negation, extreme assertion, or crisis/alert word, **THE** subtitle engine **SHALL** render that event with Vivid Coral (`&H00303BFF`) highlighting.
4. **WHEN** a subtitle event contains standard speech words, **THE** subtitle engine **SHALL** render that event with Electric Gold (`&H0000E5FF`) highlighting.
5. **WHEN** `keyword_emphasis=False` is specified or `--no-keyword-emphasis` is passed, **THE** subtitle engine **SHALL** render all active text in standard Electric Gold, preserving 100% backward compatibility.
6. **WHEN** rendering multi-word popups in `VIRAL_POPUP`, **THE** subtitle engine **SHALL NEVER** emit interior layout-splitting tags (`\c`, `\kf`), maintaining unbroken RTL runs.

## Architecture & Design

### 1. Linguistic Classification (`hawedit.captions`)
- `EmphasisCategory(Enum)`:
  - `DEFAULT`: Standard active word (Electric Gold `&H0000E5FF`)
  - `ENTITY`: Proper nouns / figures / institutions (Electric Cyan `&H00FFFF00`)
  - `ACTION_ALERT`: Negation / shock / contrast / danger (Vivid Coral `&H00303BFF`)
  - `NUMERIC`: Digits, numbers, quantifiers (Neon Emerald `&H0066FF00`)
- `classify_kurdish_emphasis(token: str) -> EmphasisCategory`:
  - Strips punctuation (`«»,.?،!:`).
  - Checks digit regex `^\d+$` and `^[٠-٩]+$`.
  - Normalizes token with `normalize_sorani` and checks against curated frozensets of Sorani keywords:
    - `_NUMERIC_KEYWORDS`: `یەک`, `دوو`, `سێ`, `چوار`, `پێنج`, `شەش`, `حەوت`, `هەشت`, `نۆ`, `دە`, `یازدە`, `دوازدە`, `بیست`, `سی`, `چل`, `پەنجا`, `شەست`, `حەفتا`, `هەشتا`, `نەوەد`, `سەد`, `هەزار`, `ملیۆن`, `ملیار`, `هەموو`, `هەمووی`, `زۆرترین`, `کەمترین`, `دووەم`, `سێیەم`.
    - `_ALERT_KEYWORDS`: `هەرگیز`, `نەخێر`, `مەحاڵە`, `کارەسات`, `مەترسی`, `مەترسیدار`, `خراپترین`, `گرنگترین`, `گەورەترین`, `سەرەکی`, `تەواو`, `ڕاستەوخۆ`, `ئاشکرا`, `بەڵێ`, `تەنانەت`, `بەڵام`.
    - `_ENTITY_KEYWORDS`: `کوردستان`, `عێراق`, `ئەمریکا`, `پێشمەرگە`, `بەغدا`, `هەولێر`, `سلێمانی`, `دهۆک`, `کەرکووک`, `پۆڵ`, `برێمەر`, `بارزانی`, `تاڵەبانی`, `سەددام`, `ئێران`, `تورکیا`.

### 2. Style Extensions (`hawedit.captions.build_ass`)
- Add style definitions for each category:
  - `KurdishCyan`, `KurdishCoral`, `KurdishEmerald`
  - Plus plate variants if `plate_intervals` provided: `KurdishCyanPlate`, `KurdishCoralPlate`, `KurdishEmeraldPlate`
  - Plus top variants if `face_intervals` provided: `KurdishTopCyan`, `KurdishTopCoral`, `KurdishTopEmerald` (+ plates)
- In `VIRAL_POPUP`:
  - Determine category of the chunk: if any word has a non-default category, map to that category style.
- In `RTL_WORD_HIGHLIGHT`:
  - When word `j == active_idx`, select style for that word according to its `classify_kurdish_emphasis(word.w)`.

### 3. Pipeline & CLI (`hawedit.pipeline`)
- Add `--keyword-emphasis / --no-keyword-emphasis` flag to CLI parser (default `True`).
- Pass `keyword_emphasis` to `build_ass`.

## Test Plan & Verification
- Unit tests in `tests/test_captions.py`:
  - Test classification of digits, Kurdish numbers, entities, alert words, and standard words.
  - Test ASS header contains category styles.
  - Test `CaptionStyle.VIRAL_POPUP` emits `KurdishCyan`, `KurdishCoral`, or `KurdishEmerald` for emphasis popups.
  - Test `CaptionStyle.RTL_WORD_HIGHLIGHT` emits category style for active emphasis word.
  - Test `keyword_emphasis=False` emits only standard `Kurdish` style.
- Gate validation: `bash scripts/verify.sh` exiting 0 with zero skipped/failed tests.
