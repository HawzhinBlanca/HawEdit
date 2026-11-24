# Impact map — Latin fallback font in Sorani captions (D7 / d7-latin-fallback-font)

Serena MCP was unavailable in this session, so all symbol callers were mapped using `rg` over `src/`, `tests/`, and living docs (`DECISIONS.md`, `BLOCKED.md`, `PROGRESS.md`). Re-run `find_referencing_symbols` before implementation if Serena becomes available.

| Symbol / artifact | Callers / references | Expected effect & test coverage |
|---|---|---|
| `captions.build_ass` (`src/hawedit/captions.py:1559`) | `pipeline.py:2410, 4300`; `assembly.py:308`; `proposals.py:596, 767, 949`; `captions.py:2721` (`mobile_caption_layout`) | All callers omitting `font_name` render with `Vazirmatn` |
| `captions.measure_rendered_caption_width` (`:967`), `wrap_caption_lines` (`:1091`), `chunk_caption_events` (`:1158`), `compute_rtl_word_positions` (`:1498`), `mobile_caption_layout` (`:2685`) | `caption_layout.py:18`, `captions.py`, `tests/test_captions.py`, `tests/test_caption_context.py` | Consistent default `Vazirmatn` font metrics across width measurement, wrapping, chunking, and layout |
| `captions.assert_ass_fonts_cover_kurdish` (`src/hawedit/captions.py:787`) | `captions.py:1042, 2555`; `render.py:1581` | Adds ASCII Latin letter check against bound font `cmap`; existing `test_captions.py:1114-1168` pass pure Sorani with `Noto Naskh Arabic` and remain unaffected |
| `release.py` (`:52-54, 951-966`), `registry.py` (`:568`), `studio_artifacts.py` (`:330`) | Wheel packaging, SPDX SBOM, and studio UI | `Vazirmatn.ttf`, `.provenance.json`, and `Vazirmatn-COPYRIGHT.txt` are already included in wheel data & SBOM; no change needed |
| `tests/test_captions.py:1401, 2440` | Assert `"Noto Naskh Arabic"` as default style row | Update to `DEFAULT_CAPTION_FONT` (`"Vazirmatn"`); explicit `font_name="Noto Naskh Arabic"` tests (`:381, 385, 1115, 1129, 1144, 1671, 1738, 1764, 1833, 1857`) stay untouched |
| `tests/golden/*.png` (4 files) + `tests/test_captions.py:542-551` | Golden render pixel tests + digest pin | Re-render and re-pin digests after `[HAWA]` approval (batched with D6/D5) |
| `DECISIONS.md` (`:16588` D-334, `:13864` D-269) | Living ADR record | Append `## D-349`; note `PROGRESS.md:477,654` and `BLOCKED.md` (no blocker) |
