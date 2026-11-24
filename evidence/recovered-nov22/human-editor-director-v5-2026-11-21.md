```yaml
commit: 0bdf80316c309bdc5a7a3f2d61bc2b399aa44440
media_sha256: ce05b824fb84dd1e5a1ad4e52124a4e9a9720783385c71fbaa7abe456726464c
host: HawaPC01 Windows-11-10.0.26300-SP0 Python-3.12.10 Dual-RTX-3090-Ti-24564MiB Driver-617.42
command: .venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4 --work-dir D:\HawEdit-media\reels\run-2026-11-21-ai-v5\work --transcript D:\HawEdit-media\reels\run-2026-11-21-ai-v5\canonical.transcript.raw.json --sentences 86,87 --verdict D:\HawEdit-media\reels\run-2026-11-21-ai-v5\work\stage4\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p-verbal-4\verdict.json --excise-fillers --silence-threshold-ms 480 --silence-target-gap-ms 160 --eased-push --progress-bar --polish-captions --encoder auto --json
```

# Human-Editor Director Engine v5 Verification (ADRs D-369–D-372, 2026-11-21)

## Provenance

- **Host:** `HawaPC01`, `Windows-11-10.0.26300-SP0`, CPython `3.12.10`, 64 CPU threads, Dual `NVIDIA GeForce RTX 3090 Ti` (`24564 MiB` each, Driver `617.42`)
- **ffmpeg:** `ffmpeg version 8.1.1-full_build-www.gyan.dev` (SHA-256 `09948d4cdd0650da6ff5a87577469f2a218dc2615ae379f8f734d24c49de0f73`), GPU 0 hardware encoder `h264_nvenc` resolved via `--encoder auto`
- **Sources:**
  - Tech/AI podcast (`ai`): `zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4` (`ce05b824fb84dd1e5a1ad4e52124a4e9a9720783385c71fbaa7abe456726464c`), canonical `5,951`-word OmniASR + CTC-3B transcript
  - Cooking/lifestyle podcast (`cooking-30m`): `zar-mjewr-cooking-with-hawzhin-2026-10-26__k_jxP903t5w__00m00-30m07__1440p.mp4` (`02bd7ed8351c70f5b1a57b3f36998c299cc1b6e72bbec51beff7250cfbd861a7`), canonical `4,524`-word OmniASR + CTC-3B transcript
- **Commits (`gemini/number-one`):**
  - `4619534`: `D-369` E3-safe Kurdish filler excision (`filler_cut_edges_ms`, expanded `KURDISH_FILLER_TOKENS`, `preserve_emphatic_repeats=True` for `زۆر زۆر`), `D-370` sub-pixel floating-point `zoompan` director motion + A/B jump-cut scale toggles + gimbal drift, `D-371` tighter 30–55 s Path A guidance, `D-372` studio filmic color grade (`eq=contrast=1.04:saturation=1.08:brightness=0.01,unsharp=3:3:0.30:3:3:0.0`) & top Studio-Gold retention progress bar
  - `0bdf803`: Replaced FFmpeg static `drawbox` `w`-expr progress bar with per-frame animated `color` + `overlay=x='-W+W*min(t/dur,1.0)'` bar and anchored `zoompan` to measured speaker `face_center_y` with `1.15×` max zoom & `0.07` horizontal drift

---

## Direct 1:1 Before (V4) vs After (V5) Multi-Genre Playback Audit

| Reel (Genre) | Version | Raw → Out Duration | Dead Air + Fillers Removed | Jump-Cuts | Kurdish Fillers Excised | Strobe Ratio (0.2–3.8 s) | Audio Loudness / TP | AV Sync Drift | Face Share | Karaoke Gold / Lime | Top Progress Bar @ 50% | Output SHA-256 Prefix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **AI `verbal-4` (`s86-87`)** | V4 (`6825946`) | `67.52 s → 65.38 s` | `2,136 ms` | `1` | `0` | `1.01×` (flat) | `-13.90 LUFS / -5.60 dBTP` | `0 ms` | `99.39%` | — | `0.0%` (none) | — |
| **AI `verbal-4` (`s86-87`)** | **V5 (`0bdf803`)** | **`67.52 s → 60.57 s`** | **`6,943 ms`** | **`8`** | **`10`** (`یەعنی`×2, `ئێ`×2, `ئا`, `ئیتر`, `بۆ نموونە`, `لەم`, `گەورەترین`) | **`1.03×`** (with zoom) | **`-13.90 LUFS / -5.70 dBTP`** | **`0 ms`** | **`99.67%`** | **`121 / 51`** (`29.7%` lime) | **`50.0%`** | `f5618cb1328f` |
| **AI `verbal-5` (`s19-22`)** | V4 (`6825946`) | `88.64 s → 86.41 s` | `2,224 ms` | `2` | `0` | `1.14×` (flat) | `-14.00 LUFS / -4.90 dBTP` | `0 ms` | `98.84%` | — | `0.0%` (none) | — |
| **AI `verbal-5` (`s19-22`)** | **V5 (`0bdf803`)** | **`88.64 s → 84.86 s`** | **`3,774 ms`** | **`6`** | **`6`** (`ئێ`×3, `بۆ نموونە`, `کە`) | **`1.05×`** (with zoom) | **`-14.00 LUFS / -4.90 dBTP`** | **`0 ms`** | **`98.35%`** | **`148 / 60`** (`28.8%` lime) | **`50.0%`** | `f4840e266a25` |
| **Cooking `topic-4` (`s7-7`)** | V4 (`6825946`) | `33.08 s → 33.08 s` | `0 ms` | `0` | `0` | `1.03×` (flat) | `-14.00 LUFS / -3.80 dBTP` | `0 ms` | `88.55%` | — | `0.0%` (none) | — |
| **Cooking `topic-4` (`s7-7`)** | **V5 (`0bdf803`)** | **`33.08 s → 30.86 s`** | **`2,224 ms`** | **`3`** | **`10`** (`نازانم چی و چی`×2, `دەست`) | **`1.14×`** (with zoom) | **`-14.00 LUFS / -3.90 dBTP`** | **`0 ms`** | **`84.52%`** | **`69 / 43`** (`38.4%` lime) | **`50.0%`** | `6bb8e3ed8d91` |

---

## Visual Frame Inspection Proof

1. **`ai-v5` `s86-87` (1080×1920 frames @ `0.2 s`, `3.4 s`, `5.0 s`, `45.0 s`):** Direct inspection confirmed smooth opening hook push-in (`0.4 s` face width `595 px` → `3.4 s` `625 px`) followed by clean A/B cam toggle back (`5.0 s` `560 px`), `1.03×` strobe ratio (zero sawtooth jitter), studio filmic color contrast, crisp Studio-Gold frame-0 hook typography, and zero karaoke ghosting.
2. **`cooking-v5` `s7-7` (1080×1920 frames @ `0.4 s`, `10.0 s`, `22.0 s`):** Direct inspection confirmed pixel-exact top Studio-Gold animated progress bar (`350 / 1080 px = 32.4%` at `10.0 s / 30.86 s`; `770 / 1080 px = 71.3%` at `22.0 s / 30.86 s`; `50.0%` at midpoint across all 3 reels), visibly tighter framing at `22.0 s`, and clean excision of both `نازانم چی و چی` filler phrases and the `دەست دەست` stutter.
3. **Human verdict discipline:** `evidence/usable-rate.csv` remains header-only (zero fabricated human verdicts).
