```yaml
commit: 9c82cc086e150fef4d0572bce974380af23d999a
media_sha256: 71c5e7943ecbfb39a8949d5be845d829eac343d897483a7b72be321d1c71d7cd
host: HawaPC01 Windows-11-10.0.26300-SP0 Python-3.12.10 Dual-RTX-3090-Ti-24564MiB Driver-617.42
command: .venv\Scripts\python.exe -m hawedit.v8 D:\HawEdit-media\excerpts\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4 --transcript D:\HawEdit-media\reels\run-2026-11-21-ai-v7\canonical.transcript.raw.json --sentences 86-87 --out-dir D:\HawEdit-media\reels\run-2026-11-22-ai-v8 --director gemini --sub-engine skia --encoder h264_nvenc
```

# V8 Lean Multimodal Content-Aware Director Verification (ADRs D-382..D-386, 2026-11-22)

## Provenance

- **Host:** `HawaPC01`, `Windows-11-10.0.26300-SP0`, CPython `3.12.10`, 64 CPU threads, Dual `NVIDIA GeForce RTX 3090 Ti` (`24564 MiB` each, Driver `617.42`)
- **ffmpeg:** `ffmpeg version 8.1.1-full_build-www.gyan.dev` (HarfBuzz + FriBidi + GPU 0 hardware encoder `h264_nvenc`)
- **Director Backend Used (Live, Zero Silent Fallback):** `GeminiVideoDirector` (`gemini-2.5-pro`, native 360p@1fps H.264 + 64 kbps 16 kHz mono AAC inline MP4 proxy + 480p@2fps Watch-Before-Ship multimodal critic) on all 3 reels.
- **Subtitle Engine Used:** `skia` (`skia-python==144.0.post2` BSD-3-Clause + `uharfbuzz==0.56.0` Apache-2.0, `Vazirmatn.ttf` `wght=800`, 1080×1920 lossless `qtrle` RGBA overlay composited via opt-in `subtitle_overlay_path` in `src/hawedit/render.py`, with sibling `.v8.ass` §4.3 validation artifact).
- **Source Media SHA-256:**
  - AI 1440p excerpt (`zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4`): `71c5e7943ecbfb39a8949d5be845d829eac343d897483a7b72be321d1c71d7cd`
  - Cooking 1440p excerpt (`zar-mjewr-cooking-with-hawzhin-2026-10-26__k_jxP903t5w__00m00-30m07__1440p.mp4`): `9a9739bc978261e8bfed6f27a8b4a8842c2693a8d929fa5797c05acabf7568d2`
- **Commit (`gemini/number-one`):** `9c82cc086e150fef4d0572bce974380af23d999a` (integrating `782aba5` D-382 schema/compiler, `91ed563` D-383 Skia+HarfBuzz TikTok subs, `dd4da09` D-384/D-386 dual-backend Director + Watch-Before-Ship critic, `b5fdc13` D-385 ASD locked shot crops, `d8b5c1b` integration + 14 hash-locked host locks + ADRs D-382..D-386 + VEX re-pin, and `9c82cc0` face-aware hook placement + multi-token repair chunk splitting + full-transcript condense sentences + critic calibration).

---

## Multi-Genre V7 → V8 Before / After Measurements (1440p → 1080×1920 NVENC)

| Reel (Genre) | V7 Dur → **V8 Dur** | Director & Critic (`D-384`/`D-386`) | Camera Restraint: Locked `1.00×` % / Moves / Locked BG Luma Diff (`D-382`) | TikTok Chunk Law: `1w / 2w / 3w / 4+` (Max 3w Visible Chars, `D-383`) | Audio-Grounded + Ortho Word Repairs | Audio Loudness / TP (2-Pass Linear) | AV Drift | Silences `>= 0.50 s` (`-35 dB`) | Face Share (V7 → **V8**, `D-385`) | Top Gold Bar @ 50% | V8 MP4 SHA-256 Prefix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **AI `s86-87`** | `59.32 s` → **`58.92 s`** | `gemini-2.5-pro`, **approved** (`0` rev) | **`82.4%` locked** / **`3` moves** / `0.41/255` (`0` sway, `1.09×` strobe) | **`37 / 71 / 15 / 0`** (`max 14` chars) | **`22`** (`ئەزانی`, `مۆدێل`, `بەیانییەکەی`, `ڕیستریکت`, `تێستی`, ...) | **`-13.9 LUFS / -5.6 dBTP`** | **`4 ms`** | **`0`** | `99.66%` → **`99.19%`** | **`50.0%`** | `0c63951159e7` |
| **AI `s19-22`** (`--condense --cold-open`) | `44.44 s` → **`43.36 s`** | `gemini-2.5-pro`, **approved** (`0` rev) | **`85.0%` locked** / **`2` moves** / `0.18/255` (`0` sway, `1.11×` strobe) | **`33 / 31 / 15 / 0`** (`max 14` chars) | **`16`** (`کوردییەکەیان`, `هەرێمی`, `تێکستێکی`, ...) | **`-14.0 LUFS / -5.2 dBTP`** | **`3 ms`** | `1` quiet beat (`0.77 s`) | `95.52%` → **`95.60%`** | **`50.0%`** | `c2d80e730ea7` |
| **Cooking `s7-7`** | `29.56 s` → **`29.20 s`** | `gemini-2.5-pro`, **approved** (`0` rev) | **`89.7%` locked** / **`1` move** / `0.59/255` (`0` sway; cross-shot luma ratio `1.83×` across real camera cut) | **`13 / 47 / 11 / 0`** (`max 14` chars) | **`6`** (`ڕێستۆرانتەکە`, `کاشێرەکە`, ...) | **`-14.0 LUFS / -4.1 dBTP`** | **`14 ms`** | **`0`** | `91.22%` → **`98.36%`** (`+7.14 pp`) | **`50.0%`** | `d07bdfe237f9` |

---

## Direct Frame-by-Frame Visual Inspection Proof (`1080×1920` PNGs)

All 12 extracted 1080×1920 frames were visually inspected directly via `read_file`, verifying **100% joined HarfBuzz Sorani Kurdish RTL glyphs**, crisp `#FFD700` Studio-Gold / `#B8FF2E` Electric-Lime active-word rounded pills with soft shadows, `0` 4-word chunks, `<= 14` visible characters on every 3-word chunk, and **zero overlap** with faces or UI margins:

1. **`ai-v8` `s86-87`** (`D:\HawEdit-media\reels\run-2026-11-22-ai-v8\frames_v8\s86-87\`):
   - `01_hook_0p6s.png`: Face-aware frosted-glass hook card `"مۆدێلە بێسنوورەکانی ژیریی دەستکرد"` cleanly placed on chest below chin (zero forehead overlap) above `"ئێستا بۆچی"` with `#FFD700` active gold pill on `ئێستا`.
   - `03_word_1.3s.png`: Repaired `"ئەزانی لەم"` (from `ئەگەزانی`) with active `#FFD700` pill on `ئەزانی`.
   - `05_power_9.5s.png`: Director-selected power word `"ڕیستریکت"` (repaired from `ڕیستیک`) inside crisp `#B8FF2E` Electric-Lime rounded pill with 100% joined Sorani letters.
   - `04_mid_29.5s.png`: Exact `50.0%` top Studio-Gold progress bar + `"ئاوا ئەسڵەن"` (`ڵ` joined cleanly).
2. **`ai-v8` `s19-22` (`--condense --cold-open`)** (`D:\HawEdit-media\reels\run-2026-11-22-ai-v8\frames_v8\s19-22\`):
   - `01_hook_0p6s.png`: Cold-open opening with frosted-glass hook card `"کاری وەرگێڕان نامێنێت بەهۆی ژیریی دەستکرد؟"` on chest cleanly above `"لەوانەیە"` gold pill.
   - `03_word_11.5s.png`: Crisp single-word `"کوردستان"` in `#FFD700` rounded pill, zero face overlap.
   - `04_mid_21.7s.png`: Exact `50.0%` top Studio-Gold progress bar + `"کاری"` on locked side-angle ASD crop.
   - `02_word_28.6s.png`: Repaired power word `"کوردییەکەیان"` in `#B8FF2E` Electric-Lime rounded pill with 100% joined HarfBuzz glyphs.
3. **`cooking-v8` `s7-7`** (`D:\HawEdit-media\reels\run-2026-11-22-cooking-v8\frames_v8\s7-7\`):
   - `01_hook_0p6s.png`: Face-aware hook card `"کێشەی پارەدانی ڕێستۆرانت چارەسەر بوو"` automatically placed in clean top headroom above speaker's head + `"کە بچینە"` gold pill.
   - `02_word_2.9s.png`: Repaired power word `"ڕێستۆرانتەکە"` (from `ڕەستۆرانتەکە`) in `#B8FF2E` Electric-Lime rounded pill, 100% joined Sorani glyphs.
   - `03_word_10.9s.png`: Repaired `"کاشێرەکە"` (from `کاشەرەکە`) in `#FFD700` gold rounded pill on locked ASD crop (`98.36%` face share).
   - `04_mid_14.6s.png`: Exact `50.0%` top Studio-Gold progress bar + `"بۆ ئەوەی"` on locked close-up reaction cut.
4. **Human verdict discipline:** `evidence/usable-rate.csv` remains header-only (`1` line; zero fabricated human verdicts).


---

## D-387 Forensic Grill Round Verification (Zero Double-Cuts, Visual Interrupts, Zero Long Silences)

- **Commit (`gemini/number-one`):** `31b567c74f1499e38d79ae05ff66af4cc2f66425` (integrating `790919d` D-387 visual interrupts + mixed BiDi, `4377e44` D-387 cut-snapped camera restraint + hyphen sanitizer + `grill_rendered_v8_video()`, `2621fa8` D-387 native/CFR exact shot cuts + zero-skew `locked_crops_to_render_inputs()`, `1c7fc31` full wiring + internal word silence exposure + `DECISIONS.md` D-387, and `31b567c` deterministic `--director-script` replay mode).
- **Director Script Provenance:** Replayed the exact saved live `gemini-2.5-pro` `.director.json` scripts from the `9c82cc0` run via explicit `--director-script` (live Gemini API returned `HTTP 429` monthly spend cap at `05:37` — strict fail-stop verified, zero silent fallback).
- **Automated Forensic Grill Gate (`grill_rendered_v8_video()`, `0.48 s` silence cap, `0.20 s` double-cut window, `0.80 s` trailing-cut guard, `0.0` audio flat factor):**

| Reel (Grilled Output) | Dur | `grill_passed` | Double-Cuts (`<= 0.20 s`) | Trailing Cuts (`<= 0.80 s`) | Silences `>= 0.48 s` (`-35 dB`) | Audio Flat Factor | Loudness / TP | AV Drift | Face Share | Chunks `1w/2w/3w/4+` (Max 3w) | Visual Interrupts & Text Verified | Grilled SHA-256 Prefix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **AI `s86-87`** (`run-2026-11-22-ai-v8-grilled`) | **`58.80 s`** | **`true`** | **`0`** (`8.00s`, `34.40s`, `51.20s` all single-frame clean) | **`0`** | **`0`** | **`0.0`** | `-13.9 LUFS / -5.5 dBTP` | `4 ms` | **`99.19%`** | `38/67/13/0` (`14`) | `15.20s` badge `لەسەر کۆمپیوتەرەکەی خۆت` + `جوابت` (hyphen stripped) + `AIـەکە` (clean BiDi) | `0c74b5ebd03e` |
| **AI `s19-22`** (`--condense --cold-open`, `run-2026-11-22-ai-v8-grilled`) | **`41.12 s`** | **`true`** | **`0`** (`2.04s`, `8.24s`, `13.88s`, `29.76s` all clean) | **`0`** | **`0`** (both `0.49s` & `0.77s` inside `'ئیشە'` removed!) | **`0.0`** | `-14.0 LUFS / -5.6 dBTP` | `17 ms` | **`100.00%`** | `33/33/14/0` (`14`) | `16.00s` badge `ژیریی دەستکرد و وەرگێڕان` above `نووسراوی` pill | `5b4590e3e4a3` |
| **Cooking `s7-7`** (`run-2026-11-22-cooking-v8-grilled`) | **`29.16 s`** | **`true`** | **`0`** (`3.08s`, `23.32s`, `27.00s` all clean) | **`0`** | **`0`** | **`0.0`** | `-14.0 LUFS / -4.1 dBTP` | `6 ms` | **`96.72%`** | `13/45/11/0` (`14`) | `3.04→3.08→3.12s` zero empty-wall flash + `ڕێستۆرانتەکە` & `بۆ ئەوەی` | `0fedc2fc3132` |

- **Direct Forensic Frame-by-Frame Inspection (`read_file` on 12 additional 1080×1920 PNGs):**
  - `D:\HawEdit-media\reels\run-2026-11-22-ai-v8-grilled\grill_frames\s86-87\{cut_7p96s,cut_8p00s,cut_8p04s,interrupt_15p20s,tok_27.16s,tok_37.21s}.png`
  - `D:\HawEdit-media\reels\run-2026-11-22-ai-v8-grilled\grill_frames\s19-22\{cut_2p00s,cut_2p04s,cut_2p08s,interrupt_16p00s}.png`
  - `D:\HawEdit-media\reels\run-2026-11-22-cooking-v8-grilled\grill_frames\s7-7\{cut_3p04s,cut_3p08s,cut_3p12s,mid_14p58s}.png`
