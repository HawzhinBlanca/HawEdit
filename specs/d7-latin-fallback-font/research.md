# Research — Latin fallback font in Sorani captions (D7 / d7-latin-fallback-font)

**Provenance.** 2026-11-18, branch `gemini/lane-4` at commit `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf`. Host `HawaPC01`, Windows 11 (`Windows-11-10.0.26300-SP0`), `.venv` CPython `3.12.10`, OpenCV `4.12.0`, `fontTools 4.60.2`, `ffmpeg 8.1.1-full_build-www.gyan.dev` (`--enable-libass`, `--enable-libharfbuzz`, `--enable-libfribidi`). Bundled fonts: `assets/fonts/NotoNaskhArabic-Regular.ttf` (`sha256:2f4b88e6ee50fa82c617e2d1d4ba18281cb1c6cd71c3af3ec64970c23995db4b`) and `assets/fonts/Vazirmatn.ttf` (`sha256:696249a2c74b39ffdef55de4df2809c5b639d3ff80d618d8160a095d2fd49dca`). Serena MCP was unavailable in this session, so all callers were mapped with `rg` over `src/` and `tests/`. Probe script and comparison grids: `specs/d7-latin-fallback-font/captures/probe_d7.py.txt`, `grid_d7_mixed_brand.png`, `grid_d7_mixed_sentence.png`.

## Defect (font-table and rendered-pixel proof)

`build_ass`, `measure_rendered_caption_width`, `wrap_caption_lines`, `chunk_caption_events`, `compute_rtl_word_positions`, and `mobile_caption_layout` all default to `font_name: str = "Noto Naskh Arabic"` (`src/hawedit/captions.py:967, 1091, 1158, 1498, 1559, 2685`).

Inspecting the bundled font tables via `fontTools.ttLib.TTFont`:

| Bundled font | Licence | `unitsPerEm` | `OS/2` weight | Kurdish required glyphs | Digits `0–9` | Latin `A–Z` / `a–z` |
|---|---|---|---|---|---|---|
| `assets/fonts/NotoNaskhArabic-Regular.ttf` | OFL-1.1 | `1000` | `400` | **Yes** | **Yes** | **No (`False`)** |
| `assets/fonts/Vazirmatn.ttf` | OFL-1.1 | `2048` | `400` (variable `wght` 100–900) | **Yes** | **Yes** | **Yes (`True`)** |

Because `NotoNaskhArabic-Regular.ttf` contains zero Latin alphabet glyphs, `libass` falls back via DirectWrite/fontconfig to a host sans-serif bold font (e.g. Arial Bold) whenever a Sorani line contains an English brand name or term.

Measured ink bounding heights on `1080x1920` renders (`img > 150` fill mask, `ffmpeg 8.1.1-full`):

| Theme / size | Font family | `"OpusClip"` ink height & px | `"2026"` height | `"کوردستان"` height | `"بەکاردەهێنین"` height | Latin/Sorani ratio (`OpusClip` / `کوردستان`) |
|---|---|---|---|---|---|---|
| `REPORT_THEME` (`64 pt`, `bold=False`) | `Noto Naskh Arabic` (fallback) | **53 px** (`2,969 px`) | 27 px | 35 px | 34 px | **1.514×** |
| `REPORT_THEME` (`64 pt`, `bold=False`) | `Vazirmatn` | **36 px** (`1,239 px`) | 27 px | 35 px | 35 px | **1.029×** |
| `VIRAL_THEME` (`108 pt`, `bold=True`) | `Noto Naskh Arabic` (fallback) | **89 px** (`12,606 px`) | 47 px | 60 px | 60 px | **1.483×** |
| `VIRAL_THEME` (`108 pt`, `bold=True`) | `Vazirmatn` | **61 px** (`4,126 px`) | 46 px | 60 px | 60 px | **1.017×** |

On `"بەکارهێنانی ChatGPT و Gemini لە کوردستان."` (`VIRAL_THEME`, 108 pt), host fallback overflows the `1080 px` frame (`x = 0..1080`), whereas `Vazirmatn` fits cleanly inside margins (`x = 105..976`, `w = 871 px`).

## Candidate analysis

1. **Candidate 1 (selected): Set `DEFAULT_CAPTION_FONT = "Vazirmatn"` across `captions.py` defaults and enforce Latin glyph coverage in `assert_ass_fonts_cover_kurdish`.**
   - `assets/fonts/Vazirmatn.ttf` is already shipped in the checkout, has `.provenance.json`, OFL-1.1 (`assets/fonts/Vazirmatn-COPYRIGHT.txt`), and SPDX/SBOM entries in `src/hawedit/release.py:52-54,951-966` and `src/hawedit/registry.py:568`. Zero new dependency, zero new font asset.
   - Harmonizes Latin and Sorani cap-heights (`1.017×` at 108 pt bold; `1.029×` at 64 pt regular) and stroke weights inside one font file.
   - `Vazirmatn` passes `assert_font_covers_kurdish` and still triggers the §4.3.6 `shaping=complex` vs `shaping=simple` negative control (`5,598` differing pixels on `GOLDEN_CAPTION_TEXT` at `64 pt`).
   - Explicit `font_name="Noto Naskh Arabic"` remains valid for pure-Sorani callers (`test_captions.py:1114`). Extending `assert_ass_fonts_cover_kurdish` to verify that any ASCII letters (`A–Z`, `a–z`) used in `[Events]` Dialogue text exist in the bound font's `cmap` ensures host Latin fallback is refused fail-stop rather than hidden.
2. **Candidate 2 (rejected): Inline `\fn` font override per Latin token.**
   - Explicitly refused by `assert_ass_fonts_cover_kurdish` (`captions.py:742`: `_INLINE_FONT_OVERRIDE`), requires bundling an extra Latin font, and splits runs.
3. **Candidate 3 (rejected): Switch to `Vazirmatn` only on events containing `[A-Za-z]`.**
   - Causes captions within the same reel to flip abruptly between Naskh (`Noto Naskh Arabic`) and geometric (`Vazirmatn`) between adjacent shots.

## Symbols and references

- `src/hawedit/captions.py`: default `font_name` parameters at `:967, 1091, 1158, 1498, 1559, 2685`; `assert_ass_fonts_cover_kurdish` (`:787-848`); `verify_caption_glyphs` (`:2538`).
- Callers relying on default `font_name`: `src/hawedit/pipeline.py:2410, 4300`, `src/hawedit/assembly.py:308`, `src/hawedit/proposals.py:596, 767, 949`.
- `tests/test_captions.py`: `:1401`, `:2440` (assert implicit default `"Noto Naskh Arabic"`), plus the four golden references (`:542-551`).
- Blueprint / ADR refs: `BLUEPRINT.md` §4.3.4, §4.3.6; `DECISIONS.md` D-133, D-163, D-334 (`:16588`).

## Risks

- **Golden image change**: Switching default `font_name` to `"Vazirmatn"` changes all four committed golden PNGs in `tests/golden/`. Requires owner `[HAWA]` approval before editing `tests/golden/*.png`.
- **VEX binding**: Editing `src/hawedit/captions.py` moves `package_digest(src/hawedit)`, requiring lead/owner VEX re-pin (`security/wsl-asr-vex.json`).
