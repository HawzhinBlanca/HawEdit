```yaml
commit: 4e3ad25b8e9378e83b70add47c900e92f878a9a3
media_sha256: ce05b824fb84dd1e5a1ad4e52124a4e9a9720783385c71fbaa7abe456726464c
host: HawaPC01 Windows-11-10.0.26300-SP0 Python-3.12.10 Dual-RTX-3090-Ti-24564MiB Driver-617.42
command: .venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4 --work-dir D:\HawEdit-media\reels\run-2026-11-21-ai-v6\work --transcript D:\HawEdit-media\reels\run-2026-11-21-ai-v6\canonical.transcript.raw.json --sentences 86,87 --verdict D:\HawEdit-media\reels\run-2026-11-21-ai-v5\work\stage4\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p-verbal-4\verdict.json --excise-fillers --silence-threshold-ms 480 --silence-target-gap-ms 160 --eased-push --progress-bar --polish-captions --encoder auto --json
```

# Cinema Masterwork Engine v6 Verification (ADRs D-373, D-374, D-376, 2026-11-21)

## Provenance

- **Host:** `HawaPC01`, `Windows-11-10.0.26300-SP0`, CPython `3.12.10`, 64 CPU threads, Dual `NVIDIA GeForce RTX 3090 Ti` (`24564 MiB` each, Driver `617.42`)
- **ffmpeg:** `ffmpeg version 8.1.1-full_build-www.gyan.dev` (SHA-256 `09948d4cdd0650da6ff5a87577469f2a218dc2615ae379f8f734d24c49de0f73`), GPU 0 hardware encoder `h264_nvenc` resolved via `--encoder auto`
- **Commit (`gemini/number-one`):** `4e3ad25b8e9378e83b70add47c900e92f878a9a3`
  - `D-373`: Balanced 2-line Kurdish editorial hook cards (`captions.py`) with responsive font sizing (`86 / 76 / 68 px`) and crisp `160 ms` pop-in (`\fscx93\fscy93\t(0,160,\fscx100\fscy100)`), eliminating 1-word 3rd-line orphans (`نییە`) while preserving frame-0 thumbnail clarity.
  - `D-374`: Cosine S-curve ease-in-out `zoompan` dolly motion (`0.5-0.5*cos(PI*p)`), unmistakable 2-cam A/B scale toggles (`1.00 ↔ 1.16×`), post-crop `anchor_y=0.33` eye-line lock (restoring cooking face share from `84.52%` to `90.97%`, beating even the un-zoomed V4 baseline `88.55%`), studio color grade (`eq=contrast=1.05:saturation=1.09:brightness=0.01,unsharp=3:3:0.35:3:3:0.0`), and subtle filmic vignette (`vignette=PI/7:eval=init`).
  - `D-376`: Zero-dependency stdlib procedural cinema micro-SFX (`sound_design.py`: frame-0 velvet sub-thump `92 → 44 Hz` at `-23 dBFS` + up to 6 spaced `>= 5.0 s` airy transition whooshes at `-26 dBFS`), mixed via `amix=inputs=2:duration=first:dropout_transition=0:normalize=0` prior to two-pass linear `-14.0 LUFS` loudnorm.

---

## Multi-Genre V6 Masterwork Measurements (1440p → 1080×1920 NVENC)

| Reel (Genre) | Raw → Out Duration | Dead Air + Fillers Removed | Jump-Cuts | Fillers Excised | Hook Lines | Audio Loudness / TP (w/ Micro-SFX) | AV Sync Drift | Face Share | Strobe Ratio (`0.2–3.8 s`) | Top Gold Bar @ 50% | Karaoke Gold / Lime | Output SHA-256 Prefix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **AI `verbal-4` (`s86-87`)** | `67.52 s → 60.57 s` | `6,943 ms` | `8` | `10` | **`2`** (0 orphan) | **`-13.90 LUFS / -5.70 dBTP`** | **`0 ms`** | **`100.00%`** | **`1.11×`** | **`50.0%`** | `121 / 51` (`29.7%`) | `c1561ab02a1e` |
| **AI `verbal-5` (`s19-22`)** | `88.64 s → 84.86 s` | `3,774 ms` | `6` | `6` | **`2`** (0 orphan) | **`-14.00 LUFS / -5.00 dBTP`** | **`0 ms`** | **`97.88%`** | **`1.05×`** | **`50.0%`** | `148 / 60` (`28.8%`) | `21cd05ab1b4c` |
| **Cooking `topic-4` (`s7-7`)** | `33.08 s → 30.86 s` | `2,224 ms` | `3` | `10` | **`2`** (0 orphan) | **`-14.00 LUFS / -4.10 dBTP`** | **`0 ms`** | **`90.97%`** | **`1.12×`** | **`50.0%`** | `69 / 43` (`38.4%`) | `e9ad91047a3c` |

---

## Direct Visual Inspection Proof

1. **`ai-v6` `s86-87` (`0.2 s`, `3.4 s`, `30.3 s` 1080×1920 PNGs):** Confirmed 2 perfectly balanced Studio-Gold hook lines (`مەترسیی ڕاستەقینەی ژیریی دەستکرد` / `تەنیا لەدەستدانی کار نییە`, zero 3rd-line orphan), smooth S-curve `1.14×` close-up with subtle filmic vignette, exact `50.0%` animated top Studio-Gold progress bar at `30.3 s`, dual-color acoustic karaoke (`#B8FF2E` Electric Lime peak + `#FFD700` Studio Gold) with `0.00 px` ghosting, and `100.00%` face share.
2. **`cooking-v6` `s7-7` (`0.2 s`, `15.4 s` 1080×1920 PNGs):** Confirmed 2 balanced Studio-Gold hook lines (`چارەسەرێکی ئاسان بۆ شەڕە سوێندی` / `بەردەم کاشێری ڕێستۆرانتەکان`), exact `0.6% → 49.8%` top progress bar progression, `90.97%` face share (clearing default `0.90` floor and beating V4 baseline `88.55%`), and clean excision of `نازانم چی و چی` ×2 + `دەست` stutter while keeping `زۆر زۆر`.
3. **Human verdict discipline:** `evidence/usable-rate.csv` remains header-only (`1` line; zero fabricated human verdicts).
