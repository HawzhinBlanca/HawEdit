# Impact Map — Keyword Emphasis & Multi-Color Kinetic Subtitles

## Affected Symbols and Modules

### 1. `src/hawedit/captions.py`
- **New Symbols**:
  - `EmphasisCategory`: Enum with values `DEFAULT`, `ENTITY`, `ACTION_ALERT`, `NUMERIC`.
  - `classify_kurdish_emphasis(token: str) -> EmphasisCategory`: Pure Python/regex classifier for Kurdish tokens.
  - Category V4+ Styles:
    - `KurdishCyan` (`PrimaryColour=&H00FFFF00`), `KurdishCoral` (`PrimaryColour=&H00303BFF`), `KurdishEmerald` (`PrimaryColour=&H0066FF00`).
    - Plate variants: `KurdishCyanPlate`, `KurdishCoralPlate`, `KurdishEmeraldPlate`.
    - Top variants (face collision): `KurdishTopCyan`, `KurdishTopCoral`, `KurdishTopEmerald` (+ plate equivalents).
- **Modified Symbols**:
  - `build_ass`: Add `keyword_emphasis: bool = True` argument.
    - Adds new Category styles to `[V4+ Styles]` block.
    - In `CaptionStyle.VIRAL_POPUP`: Selects style based on chunk word category.
    - In `CaptionStyle.RTL_WORD_HIGHLIGHT`: Selects active word style based on word category.
  - `__all__`: Export `EmphasisCategory`, `classify_kurdish_emphasis`.

### 2. `src/hawedit/pipeline.py`
- **Modified Symbols**:
  - `run_pipeline`: Accept `keyword_emphasis: bool = True` parameter.
  - CLI parser in `main()` / `_build_parser()`: Add `--keyword-emphasis` and `--no-keyword-emphasis` flags (default `True`).
  - Pass `keyword_emphasis` to `build_ass(...)`.

### 3. `src/hawedit/editor_agent.py`
- **Modified Symbols**:
  - `EditorParameters`: Add `keyword_emphasis: bool = True`.

### 4. `tests/test_captions.py`
- **New Tests**:
  - `test_classify_kurdish_emphasis_identifies_numbers`: Verifies Arabic/Latin/spelled-out numerals.
  - `test_classify_kurdish_emphasis_identifies_entities`: Verifies key proper nouns and entities.
  - `test_classify_kurdish_emphasis_identifies_action_alerts`: Verifies negation and shock/danger words.
  - `test_classify_kurdish_emphasis_defaults_to_neutral`: Verifies standard words return `DEFAULT`.
  - `test_build_ass_with_keyword_emphasis_viral_popup`: Asserts category style applied to popup events.
  - `test_build_ass_with_keyword_emphasis_rtl_word_highlight`: Asserts active word uses category style.
  - `test_build_ass_disabled_keyword_emphasis_retains_standard_styles`: Asserts backward compatibility when `keyword_emphasis=False`.

## Callers and Ripple Effects
- Callers of `build_ass`:
  - `pipeline.py`: Passes `keyword_emphasis`.
  - `assembly.py`: Uses default (`keyword_emphasis=True` or `False`).
  - Existing tests in `tests/test_captions.py`, `tests/test_render.py`, `tests/test_delivery.py`: `keyword_emphasis` defaults to `True` or `False` safely; existing style names (`Kurdish`, `KurdishDim`, etc.) remain intact and untouched.
