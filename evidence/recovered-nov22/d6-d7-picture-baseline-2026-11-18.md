```yaml
commit: 1714a8b1312299fc62835bdc4bdaae7fdd30e7bf
media_sha256: 6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0
host: HawaPC01
command: .venv\Scripts\python.exe specs\d6-rtl-karaoke-fill\captures\probe_d6.py.txt specs\d6-rtl-karaoke-fill\captures && .venv\Scripts\python.exe specs\d7-latin-fallback-font\captures\probe_d7.py.txt specs\d7-latin-fallback-font\captures && .venv\Scripts\python.exe specs\d5-phone-readable-captions\captures\probe_d5.py.txt specs\d5-phone-readable-captions\captures && .venv\Scripts\python.exe specs\d8-cut-audio-fades\captures\probe_d8.py.txt specs\d8-cut-audio-fades\captures
```

# Lane 4 Picture Baseline Measurements (D6, D7, D5, D8) — 2026-11-18

**Environment & Provenance:**
- Machine: `HawaPC01`, OS `Windows-11-10.0.26300-SP0`
- Python: `3.12.10` (`.venv\Scripts\python.exe`)
- Libraries: `opencv-python-headless` (`cv2`) `4.12.0`, `fontTools` `4.60.2`
- Renderer: `ffmpeg 8.1.1-full_build-www.gyan.dev` (`--enable-libass`, `--enable-libharfbuzz`, `--enable-libfribidi`)
- Git commit: `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf` (`gemini/lane-4`)
- Fonts:
  - `assets/fonts/NotoNaskhArabic-Regular.ttf`: `sha256:2f4b88e6ee50fa82c617e2d1d4ba18281cb1c6cd71c3af3ec64970c23995db4b`
  - `assets/fonts/Vazirmatn.ttf`: `sha256:696249a2c74b39ffdef55de4df2809c5b639d3ff80d618d8160a095d2fd49dca`
- Media inputs:
  - `tests/fixtures/kurdish-speech-3cuts.mp4`: `sha256:ed038e743a6b1ee167290741ceda926ac1077ff192e4910528017e3183655a15`
  - `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4`: `sha256:6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0`
  - `D:\HawEdit-media\sources\zar-mjewr-cooking-with-hawzhin-2026-10-26__k_jxP903t5w.mp4`: `sha256:b594c941d7a95dbf68b6eee9fb103c14bead4593ef9ed3cf7ae3ee848221b273`

## 1. D6 — `\kf` Highlight Sweep Inside Sorani Words (`specs/d6-rtl-karaoke-fill/captures/`)

Tested on `GOLDEN_CAPTION_TEXT` (`"ڕۆژنامەوانی کوردی لە هەولێر."`, `VIRAL_THEME`, 108 pt, `Noto Naskh Arabic`), word 0 (`x = 581..898`, `0..600 ms`):

- **Baseline `WORD_HIGHLIGHT` (`\kf`):**
  - `t=0.15 s`: gold `x=581..661` (mean `627.1`), white `x=668..896` (mean `788.9`) -> **LTR (wrong)**
  - `t=0.30 s`: gold `x=581..751` (mean `667.9`), white `x=753..896` (mean `829.2`) -> **LTR (wrong)**
  - `t=0.45 s`: gold `x=581..817` (mean `699.3`), white `x=818..896` (mean `856.5`) -> **LTR (wrong)**
  - `t=1.50 s` (`هەولێر.`): gold `x=184..271` (mean `233.2`), white `x=272..343` (mean `309.7`) -> **LTR (wrong)**
- **Candidate two-layer animated `\clip` (`clip_bord4`):**
  - `t=0.15 s`: gold `x=816..896` (mean `855.6`), white `x=581..815` (mean `699.0`) -> **RTL**
  - `t=0.30 s`: gold `x=728..896` (mean `820.5`), white `x=581..727` (mean `658.8`) -> **RTL**
  - `t=0.45 s`: gold `x=668..896` (mean `788.4`), white `x=581..661` (mean `627.2`) -> **RTL**
  - `t=0.80 s` (`کوردی`): gold `x=492..560` (mean `528.3`), white `x=421..489` (mean `451.3`) -> **RTL**
  - `t=1.50 s` (`هەولێر.`): gold `x=258..343` (mean `303.3`), white `x=184..252` (mean `226.5`) -> **RTL**
  - Mixed `"OpusClip زۆر باشە."`: `"OpusClip"` sweeps LTR (`mean_x: 494.5 -> 545.8 -> 586.3`), `"زۆر"` and `"باشە."` sweep RTL (`398.8 > 365.4`, `298.8 > 245.1`).
  - Outline parity at `t=1.90 s` vs single-layer gold render: `max_diff = 0`, `diff_pixels(>5) = 0` (`bord0` had `3,456` fringe pixels).

## 2. D7 — Latin Fallback Font (`specs/d7-latin-fallback-font/captures/`)

`NotoNaskhArabic-Regular.ttf` lacks all Latin `A–Z`/`a–z` codepoints (`fontTools` cmap check: `False`); `Vazirmatn.ttf` (OFL-1.1, already bundled) covers Kurdish required glyphs, digits `0–9`, and Latin `A–Z`/`a–z`.

- `REPORT_THEME` (`64 pt`, `bold=False`):
  - `Noto Naskh Arabic` (host fallback): `"OpusClip"` `53 px` tall (`2,969 px`) vs `"کوردستان"` `35 px` (`1.514×` ratio)
  - `Vazirmatn`: `"OpusClip"` `36 px` tall (`1,239 px`) vs `"کوردستان"` `35 px` (`1.029×` ratio)
- `VIRAL_THEME` (`108 pt`, `bold=True`):
  - `Noto Naskh Arabic` (host fallback): `"OpusClip"` `89 px` tall (`12,606 px`) vs `"کوردستان"` `60 px` (`1.483×` ratio)
  - `Vazirmatn`: `"OpusClip"` `61 px` tall (`4,126 px`) vs `"کوردستان"` `60 px` (`1.017×` ratio)
- `Vazirmatn` `shaping=complex` vs `shaping=simple` on `GOLDEN_CAPTION_TEXT`: `5,598` differing pixels.

## 3. D5 — Phone-Readable Sizing & Protected Zar Regions (`specs/d5-phone-readable-captions/captures/`)

- Over real `zar-ai-lamo` `9:16` crop (`"ژیری دەستکرد داهاتووە."`):
  - `64 pt` `REPORT_THEME` (`Noto`): `ink_h = 35 px`, `y_center = 1748 px`
  - `108 pt` `VIRAL_THEME` (`Noto`): `ink_h = 59 px`, `y_center = 1506 px`
  - `128 pt`, `outline=6.0`, `margin_v=450` (`Vazirmatn`): `ink_h = 72 px` (`2.06×` of 64 pt), `ink_w = 702 px`, `y_center = 1405 px`
- Real Zar Podcast obstacles in `1080x1920` crop:
  - Cooking teaser `"لەم پۆدکاستەدا:"` pill (`zar-mjewr-cooking`, `t = 5.0 s`): `x = 68..1013`, `y = 1525..1734` (`0.794..0.903`) — collides with `margin_v=360` (`y_center=1506`), cleared by `margin_v=450` (`y_center=1405`) and protected by `SOURCE_ON_SCREEN_TEXT`.
  - AI excerpt wide two-shot (`zar-ai-lamo`, `t = 35 s, 110 s`): table/rug/props occupy `y = 1060..1920` (`0.55..1.00`), requiring `ProtectedRegionKind.TABLE_OBJECT` wired via `plan_caption_layout`.

## 4. D8 — Cut Audio Fades (`specs/d8-cut-audio-fades/captures/`)

Measured on `48 kHz` mono PCM (`ffmpeg`) comparing raw `atrim`+`concat` vs `30 ms` `qsin` `afade`:

- Fixture (`kurdish-speech-3cuts.mp4`, `2000..3200` + `200..1200`, cut `1.200 s`): duration `2200.0 ms` (`mp4=2200 ms`) in both; `boundary_1ms_peak` `0.06064 -> 0.00165` (`36.8×` reduction), `tight_max_step` `0.03880 -> 0.00934` (`4.15×` reduction).
- Zar AI excerpt (`5.0..8.5 s` + `18.0..21.5 s`, cut `3.500 s`): duration `7020.0 ms` in both; `boundary_1ms_peak` `0.23853 -> 0.00975` (`24.5×` reduction), `tight_max_step` `0.04150 -> 0.00259` (`16.0×` reduction).
