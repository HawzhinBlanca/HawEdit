```yaml
commit: fd86c359bd3f9edcb8ba2c942a15ff812f0312d5
media_sha256: 71c5e7943ecbfb39a8949d5be845d829eac343d897483a7b72be321d1c71d7cd
host: HawaPC01 Windows-11-10.0.26300-SP0 Python-3.12.10 Dual-RTX-3090-Ti-24564MiB Driver-617.42
command: .venv\Scripts\python.exe -m hawedit.v8 episode D:\HawEdit-media\excerpts\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4 --transcript D:\HawEdit-media\reels\run-2026-11-21-ai-v7\canonical.transcript.raw.json --out-dir D:\HawEdit-media\reels\run-2026-11-22-client-ai-v9 --max-clips 3 --style-preset viral_gold --condense --cold-open --director offline --sub-engine skia --encoder h264_nvenc
```

# V9 Client-Ready Production Suite Verification (ADRs D-388..D-392, 2026-11-22)

## Provenance

- **Host:** `HawaPC01`, `Windows-11-10.0.26300-SP0`, CPython `3.12.10`, 64 CPU threads, Dual `NVIDIA GeForce RTX 3090 Ti` (`24564 MiB` each, Driver `617.42`)
- **ffmpeg:** `ffmpeg version 8.1.1-full_build-www.gyan.dev` (HarfBuzz + FriBidi + GPU 0 hardware encoder `h264_nvenc`)
- **Source Media SHA-256:**
  - AI 1440p excerpt (`zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4`): `71c5e7943ecbfb39a8949d5be845d829eac343d897483a7b72be321d1c71d7cd`
  - Cooking 1440p excerpt (`zar-mjewr-cooking-with-hawzhin-2026-10-26__k_jxP903t5w__00m00-30m07__1440p.mp4`): `9a9739bc978261e8bfed6f27a8b4a8842c2693a8d929fa5797c05acabf7568d2`
- **Commit (`gemini/number-one`):** `fd86c359bd3f9edcb8ba2c942a15ff812f0312d5` (integrating `0d046a4` D-388 5 curated style presets + speaker bio + end card, `645957a` D-389/D-390 full-episode multi-reel compiler + client delivery pack + HTML review gallery, `c6dcaf9` D-391 team preflight `doctor` + hardened `LocalOmniDirector`, `19c10e5` D-392 Studio Web V8/V9 API & UI, `4fc436c` full V9 wiring + ADRs D-388..D-392 + VEX re-pin, and `fd86c35` root-cause ASD crop coalescing fix in `snap_locked_crops_to_cuts()`).
- **Live LLM Probes (Honest Strict Fail-Stop, Zero Silent Fallback):**
  - Live `GeminiVideoDirector` (`gemini-2.5-pro`) returned `HTTP 403 PERMISSION_DENIED` on `2026-11-22`; live `LocalOmniDirector` (`--local-modality text`, `huihui-deepseek-v4-flash-0731-abliterated` on `127.0.0.1:1234`) timed out at `240 s`. Both failed loudly with exit code `2` and zero silent fallback to offline heuristics.
  - Multi-preset client variety reels (`luxury_minimal`, `crimson_punch`, `broadcast_news`, `executive_cyan`) deterministically replayed the saved `gemini-2.5-pro` `.director.json` scripts from `run-2026-11-22-*-v8-grilled` via `--director-script`; the 3-reel full-episode batch (`viral_gold`) used explicit `--director offline`.

---

## Check A — Live Team Preflight `python -m hawedit.v8 doctor` (`HawaPC01`, 679 ms)

- `gpu_nvenc`: **OK** (`579 ms`) — `h264_nvenc ready - GPU 0: NVIDIA GeForce RTX 3090 Ti (6357/24564 MiB free); GPU 1: NVIDIA GeForce RTX 3090 Ti (23665/24564 MiB free)`
- `ffmpeg_rtl`: **OK** (`54 ms`) — `FFmpeg RTL stack verified (libass + HarfBuzz + FriBidi) at ffmpeg.EXE`
- `skia_harfbuzz`: **OK** (`97 ms`) — `skia 144.0.post2 + uharfbuzz 0.56.0 ready; Vazirmatn.ttf covers Sorani Kurdish`
- `wsl_asr`: **OK** (`54 ms`) — `WSL ASR healthy on 2/2 endpoints (kurdish-omniasr-7b)`
- `gemini_director`: **OK** (`0 ms`) — `GEMINI_API_KEY configured (secret redacted)`
- `local_omni_director`: **OK** (`50 ms`) — `Local LLM ready at http://127.0.0.1:1234/v1/models (2 model(s): huihui-deepseek-v4-flash-0731-abliterated, qwen3.8-27b-obliterated)`
- `disk_space`: **OK** (`1 ms`) — `753.6 GB free / 1863.0 GB total on D:\HawEdit-media`
- **Verdict:** `7 ok, 0 warn, 0 fail | ready_for_production=True`

---

## Checks B, C & D — Real 1440p Multi-Client Production Proof & Forensic Grill (`7 / 7` Passed)

During the first Check B run on `r02-s86-87` (`--condense --cold-open`), the permanent forensic grill gate (`D-387`) caught a real 1-frame crop delay flash (`9.84s -> 9.88s`): adjacent identical silence-trimmed crop spans emitted a no-op boundary (`9668 ms`) that stole exact CFR cut `9840 ms` from the real `928 -> 484` switch (`9854 ms`). Root-cause fix `fd86c35` coalesces contiguous identical crops inside `snap_locked_crops_to_cuts()` before CFR snapping, eliminating the flash cleanly.

| Client Pack & Reel | Style Preset & Brand Kit | Dur | `grill_passed` | Double / Trailing / Silences `>= 0.48 s` | Audio Flat | Loudness / TP | Face Share | Camera Policy Verified | Chunks `1w/2w/3w/4+` (`max 3w`) | `.overlay.mov` Reclaimed (`0` Left) | SHA-256 Prefix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **AI Episode `r01-s38-40`** (`run-2026-11-22-client-ai-v9`) | `viral_gold` (`episode` batch, `--condense --cold-open`) | `37.34 s` | **`true`** | **`0 / 0 / 0`** | `0.0` | `-13.96 LUFS / -6.54 dBTP` | `100.0%` | `0` moves (`100%` locked) | `24 / 66 / 15 / 0` (`14`) | `36.98 MB` | `d4cdfe34fad2` |
| **AI Episode `r02-s86-87`** (`run-2026-11-22-client-ai-v9`) | `viral_gold` (`episode` batch, `--condense --cold-open`) | `60.65 s` | **`true`** | **`0 / 0 / 0`** | `0.0` | `-14.01 LUFS / -5.64 dBTP` | `100.0%` | `3` moves (`<= 1.14×`) | `41 / 106 / 33 / 0` (`14`) | `59.15 MB` | `8d842b67883f` |
| **AI Episode `r03-s7-9`** (`run-2026-11-22-client-ai-v9`) | `viral_gold` (`episode` batch, `--condense --cold-open`) | `35.22 s` | **`true`** | **`0 / 0 / 0`** | `0.0` | `-14.00 LUFS / -5.93 dBTP` | `100.0%` | `1` move (`<= 1.14×`) | `20 / 56 / 24 / 0` (`14`) | `34.81 MB` | `326c2b838eba` |
| **Cooking `s7-7`** (`run-2026-11-22-client-cooking-v9`) | `luxury_minimal` + Speaker Bio (`هاوژین` / `پێشکەشکار`) + Outro (`@hawedit`) | `29.16 s` | **`true`** | **`0 / 0 / 0`** | `0.0` | `-14.06 LUFS / -4.06 dBTP` | `100.0%` | `0` moves (`<= 1.08×` cap) | `13 / 74 / 24 / 0` (`14`) | `43.42 MB` | `8caf756dcb3d` |
| **Creator `s86-87`** (`run-2026-11-22-client-creator-v9`) | `crimson_punch` (`--director-script` Gemini replay) | `58.80 s` | **`true`** | **`0 / 0 / 0`** | `0.0` | `-14.03 LUFS / -5.54 dBTP` | `100.0%` | `3` moves (`<= 1.15×`) | `38 / 106 / 30 / 0` (`14`) | `73.78 MB` | `af39429f541b` |
| **News `s19-22`** (`run-2026-11-22-client-news-v9`) | `broadcast_news` (`--condense --cold-open`, Gemini replay) | `41.14 s` | **`true`** | **`0 / 0 / 0`** | `0.0` | `-14.00 LUFS / -5.56 dBTP` | `100.0%` | **`0` moves (`100%` locked `1.00×`!)** | `33 / 54 / 24 / 0` (`14`) | `48.71 MB` | `23b42b9f9676` |
| **Executive `s19-22`** (`run-2026-11-22-client-exec-v9`) | `executive_cyan` (`--condense --cold-open`, Gemini replay) | `41.14 s` | **`true`** | **`0 / 0 / 0`** | `0.0` | `-14.00 LUFS / -5.56 dBTP` | `100.0%` | **`2` moves clamped to `<= 1.08×`** | `33 / 54 / 24 / 0` (`14`) | `38.97 MB` | `bce1bf1c4307` |

- **Total temporary `.v8.overlay.mov` reclaimed:** **`335.82 MB`** across 7 reels (`0` leftover `.overlay.mov` files in any client output directory).
- **Complete Client Delivery Pack Verified on 7 / 7 Reels:** Every reel directory contains non-empty `.v8.mp4`, `.v8.srt`, `.v8.edl`, `.v8.otio`, `.v8.cover.png`, `.director.json`, `.grill.json`, and self-contained `client-review.html` (plus `episode.v8.json` for Check B).

---

## Direct Frame-by-Frame Visual Inspection (`12` Real `1080×1920` PNGs Audited via `read_file`)

1. **Check B `viral_gold` covers & mid-frame:** `r01-s38-40.v8.cover.png`, `r02-s86-87.v8.cover.png`, `r03-s7-9.v8.cover.png`, `v9_visual_audit_frames/01_viral_gold_mid.png` — face-aware hook cards, `#FFD700` active gold pills, 100% joined HarfBuzz Sorani glyphs, zero forehead overlap.
2. **Check C `luxury_minimal` + Speaker Bio + Outro CTA:** `s7-7.v8.cover.png`, `02_luxury_minimal_speaker_bio.png` (`هاوژین` / `پێشکەشکار` dark-glass RTL lower-third with champagne-gold right bar, zero overlap with obsidian/gold pill `"کەسە ئەڵێم"`), `03_luxury_minimal_end_card.png` (frosted outro CTA `"بەشداربن بۆ ڤیدیۆی زیاتر"` + `"پۆدکاستی چێشتلێنان"` + `@hawedit` pill cleanly above `"و ئەوانە"`).
3. **Check C `crimson_punch`:** `s86-87.v8.cover.png` (`#FF2E63` crimson pill + white `"ئێستا"` + crimson-trimmed hook card), `04_crimson_punch_interrupt.png` (crimson-bordered `"لەسەر کۆمپیوتەرەکەی خۆت"` above `#FFD700` power pill `"لۆکەڵی"`).
4. **Check C `broadcast_news`:** `s19-22.v8.cover.png`, `05_broadcast_news_interrupt.png` (royal-blue `#1D4ED8` progress bar, deep-navy `#102446` + `#FFD700` gold-trimmed interrupt `"ژیریی دەستکرد و وەرگێڕان"` and pill `"نووسراوی"`, 100% locked `1.00×` tripod).
5. **Check C `executive_cyan`:** `s19-22.v8.cover.png` (`#00D4FF` cyan pill + `#07131C` ink `"لەوانەیە"` + cyan-bordered dark-navy hook card, moves clamped to `1.08×`).

---

## Check E — Live Studio Web Server Smoke Test (`hawedit.web`, `127.0.0.1:55968`)

- `GET /`: HTTP `200` (`73,786` bytes HTML containing `#v8HealthStrip`, `#stylePresetGrid`, `#clientBrandKit`, `GRILL PASSED`, `/api/v8/doctor`, `/api/v8/presets`).
- `GET /api/v8/doctor`: HTTP `200`, `ready_for_production: true`, `7 ok / 0 warn / 0 fail`.
- `GET /api/v8/presets`: HTTP `200`, all 5 presets (`viral_gold`, `crimson_punch`, `executive_cyan`, `luxury_minimal`, `broadcast_news`) with swatches.
- Clean server shutdown & private temp storage teardown verified.
- **Human QC Discipline:** `evidence/usable-rate.csv` remains header-only (`1` line; zero fabricated human verdicts).
