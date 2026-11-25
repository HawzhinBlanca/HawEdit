# Plan — Latin fallback font in Sorani captions (D7 / d7-latin-fallback-font)

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"

Read `research.md` and `spec.md` first. Captures and probe script: `captures/grid_d7_mixed_brand.png`, `captures/grid_d7_mixed_sentence.png`, `captures/probe_d7.py.txt`.

## Approach

Eliminate host-font Latin fallback cleanly using the bundled OFL-1.1 `Vazirmatn.ttf` already present in `assets/fonts/`:

1. **`DEFAULT_CAPTION_FONT: Final = "Vazirmatn"`** in `src/hawedit/captions.py`, used as the default `font_name` in `measure_rendered_caption_width`, `wrap_caption_lines`, `chunk_caption_events`, `compute_rtl_word_positions`, `build_ass`, and `mobile_caption_layout`. Keep `NotoNaskhArabic-Regular.ttf` in `assets/fonts/` so callers explicitly passing `font_name="Noto Naskh Arabic"` for pure-Sorani ASS continue to resolve and pass.
2. **Fail-stop Latin glyph guard in `assert_ass_fonts_cover_kurdish` (`src/hawedit/captions.py:787`)**: extract any ASCII Latin letters (`[A-Za-z]`) present in Dialogue text (after stripping ASS override tags) and verify they exist in the bound directory font's `cmap`, raising `FontCoverageError` if absent so host-font fallback can never sneak back in silently.
3. **Update the two tests pinning the old default font (`tests/test_captions.py:1401, 2440`)** and re-render the four golden references (`tests/golden/*.png`) **only after owner `[HAWA]` approval**, updating `GOLDEN_DIGESTS`.

No new dependency, no new font file, no new ADR licence risk (`Vazirmatn.ttf` is already OFL-1.1 and audited in `release.py`/`registry.py`).

## Files and symbols

| File | Symbol | Change |
|---|---|---|
| `src/hawedit/captions.py` | `DEFAULT_CAPTION_FONT`, `measure_rendered_caption_width` (`:967`), `wrap_caption_lines` (`:1091`), `chunk_caption_events` (`:1158`), `compute_rtl_word_positions` (`:1498`), `build_ass` (`:1559`), `mobile_caption_layout` (`:2685`) | Default `font_name` changed from `"Noto Naskh Arabic"` to `DEFAULT_CAPTION_FONT` (`"Vazirmatn"`) |
| `src/hawedit/captions.py` | `assert_ass_fonts_cover_kurdish` (`:787`) | Require bound font `cmap` to cover any `[A-Za-z]` letters in Dialogue events |
| `tests/test_captions.py` | `:1401`, `:2440`, new AC1–AC3 tests | Update default font expectation to `DEFAULT_CAPTION_FONT`; add height-ratio and fail-stop coverage tests |
| `tests/golden/*.png` (4 files) + `tests/test_captions.py:542-551` | — | Re-render and update `GOLDEN_DIGESTS` **only with owner `[HAWA]` approval** |
| `DECISIONS.md` | `## D-349` | Record switch of default caption font from `Noto Naskh Arabic` to bundled `Vazirmatn` |

## Divergence and ADR

Implements `BLUEPRINT.md` §4.3.4 (zero host font fallback) and §4.3.6; no divergence from `BLUEPRINT.md`. Documented in **D-349**.

## Risks and owner actions

1. **Owner approval (`[HAWA]`)**: Replacing the four golden PNGs (`kurdish-caption.png`, `kurdish-viral-karaoke.png`, `kurdish-hook-card.png`, `kurdish-caption-fixture.png`) under `.codystem-allow-self-edit` (batched with D6 and D5 so goldens are updated once).
2. **VEX binding**: Editing `src/hawedit/captions.py` moves `package_digest(src/hawedit)`, requiring lead/owner re-pin of `security/wsl-asr-vex.json`.
3. **CI Linux `libass`**: Variable font `Vazirmatn.ttf` bold rendering (`Bold = 1`) on Linux zackees ffmpeg v8.0 will be verified by CI's golden comparisons.
