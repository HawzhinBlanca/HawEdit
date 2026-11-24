```yaml
commit: 066e420df0083edc6d9033734ceb200027126440
media_sha256: 71c5e7943ecbfb39a8949d5be845d829eac343d897483a7b72be321d1c71d7cd
host: HawaPC01 Windows-11-10.0.26300-SP0 Python-3.12.10 Dual-RTX-3090-Ti-24564MiB Driver-617.42
command: .venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4 --work-dir D:\HawEdit-media\reels\run-2026-11-21-ai-v7\work --transcript D:\HawEdit-media\reels\run-2026-11-21-ai-v7\canonical.transcript.raw.json --sentences 19,20,21,22 --verdict D:\HawEdit-media\reels\run-2026-11-21-ai-v5\work\stage4\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p-verbal-5\verdict.json --condense --cold-open --ingest-threads 0 --excise-fillers --silence-threshold-ms 480 --silence-target-gap-ms 160 --eased-push --progress-bar --polish-captions --encoder auto --json
```

# V7 Masterpiece Engine Verification (ADRs D-377..D-381, 2026-11-21)

## Provenance

- **Host:** `HawaPC01`, `Windows-11-10.0.26300-SP0`, CPython `3.12.10`, 64 CPU threads, Dual `NVIDIA GeForce RTX 3090 Ti` (`24564 MiB` each, Driver `617.42`)
- **ffmpeg:** `ffmpeg version 8.1.1-full_build-www.gyan.dev` (SHA-256 `09948d4cdd0650da6ff5a87577469f2a218dc2615ae379f8f734d24c49de0f73`), GPU 0 hardware encoder `h264_nvenc` resolved via `--encoder auto`
- **Commit (`gemini/number-one`):** `066e420df0083edc6d9033734ceb200027126440` (integrating `b0a9658` D-377, `90f82aa` D-378, `200cb37` D-379/D-380, `49bafb4` D-381, `0732bfd` pipeline/VEX wiring, `89aa86f` assembled boundary sync, `4ae1e6e` assembled `time_mapping` + multithreaded decode, and `066e420` 1 ms hold-and-step splice camera cuts)
  - `D-377`: Pure-stdlib `tighten_ctc_word_onsets()` (`silence.py`) exposing CTC-stretched pre-word pauses (including brief `<= 60 ms` weak release-bleed skipping) and trailing unvoiced tails before `plan_silence_tightening()`.
  - `D-378`: Opt-in `--condense` and `--cold-open` flags wired via `plan_viral_story_cut()` (`assembly.py` + `condenser.py`), pruning low-scoring middle-tangent sentences down to `30–48 s`, prepending a `1.8–3.4 s` E3-safe payoff cold-open hook (`0` split words), splicing interior silence/filler cuts per body span, applying 1 ms hold-and-step camera cuts across splices, and computing exact two-pass `-14.0 LUFS` linear loudness over assembled spans.
  - `D-379`: `extract_kurdish_callout_cards()` + `CALLOUT_CARD_THEME` (`captions.py`), auto-wired when `cinema_plan is not None`, emitting Layer 2 face-aware Electric-Lime (`#B8FF2E`) 1–3 word Kurdish kinetic callout cards (`>= 4.5 s` clear of hook card, spaced `>= 10 s`).
  - `D-380`: Zero-ghosting `kinetic_entrance=True` (`\fad(50,0)` on Layer 0 + Layer 4 `\clip` = `0.00 px` displacement) + vertical `\move` micro-lift strictly on non-clipped `Hook` (`12 px`), `Callout` (`14 px`), and `SpeakerTag` (`12 px`, smooth `\fad(180,250)`).
  - `D-381`: Deterministic Sorani ASR orthography + bigram repair (`KURDISH_ASR_ORTHOGRAPHY_FIXES`, `KURDISH_ASR_BIGRAM_FIXES`, consonant+`ی` double-yaa rule in `caption_polish.py`) always active under `--polish-captions` (preserving 1:1 CTC timestamps and immutable `raw.json`) plus pure-stdlib fail-loud `LocalLlmJsonClient` (`HAWEDIT_LOCAL_LLM_URL`).
- **Storage integrity observation (`D:` drive excerpts):** Between the V6 run (`2026-11-21 22:20`) and V7 run (`2026-11-21 23:54`), the unmodified 2.56 GB AI 1440p excerpt shifted SHA-256 from `ce05b824...` to `71c5e794...` (with one H.264 decode warning `error while decoding MB 146 86, bytestream 633`) and the 2.09 GB Cooking 1440p excerpt shifted from `02bd7ed8...` to `9a9739bc...` (matching an earlier `v2 -> v3` shift on the same `ST2000VX008` HDD). Decoded 16 kHz PCM Stage 0 `audio.wav` was independently verified **100% bit-for-bit identical** for both episodes (AI: `76,534,254` bytes, SHA-256 `81cdd22d82b88f7dd282cdd17239a47a55092b9834bcb9fb342ddaa79118459c`; Cooking: `57,824,494` bytes, SHA-256 `ebb22b5547104421444a444d148e5cc0fa9d6b23c7ddb7343044496b8046d5e8`). V7 run-dir copies of `canonical.transcript.raw.json` were bound to the observed disk hashes; all V6 artifacts remain untouched.

---

## Multi-Genre V6 → V7 Before / After Measurements (1440p → 1080×1920 NVENC)

| Reel (Genre) | Raw → V6 → **V7 Duration** | Silences `>= 0.50 s` (`-35 dB`) V6 → **V7** | Callout Cards (V6 → **V7**) | Repaired Sorani Words Verified On-Screen | Audio Loudness / TP (2-Pass Linear) | AV Sync Drift | Face Share (Default `0.90` Floor) | Strobe Ratio | Top Gold Bar @ 50% | V7 Output SHA-256 Prefix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **AI `verbal-4` (`s86-87`)** | `67.52 s` → `60.57 s` → **`59.32 s`** (`-1,239 ms` extra dead air cut) | `1` (`0.79 s` `'نازانی'`) → **`0`** | `0` → **`4`** | `6` (`ئەزانی`, `مۆدێل`, `بەیانییەکەی`, `ڕێگرییەکانی`, `زانیارییەکان`, `ڕیستریکت`) | **`-13.9 LUFS / -5.7 dBTP`** | **`0 ms`** | **`99.66%`** | **`1.07×`** (`0.2–3.8 s`) | **`50.0%`** | `0b296cdec5e3` |
| **AI `verbal-5` (`s19-22`, `--condense --cold-open`)** | `88.64 s` → `84.86 s` → **`44.44 s`** (`-44.20 s` condensed + `2.61 s` cold-open hook) | `1` quiet beat (`0.77 s` inside `'ئیشە'`) | `0` → **`3`** | `3` (`کوردییەکەیان` ×2 incl. cold open, `هەرێمی`, `تێکستێکی`) | **`-14.0 LUFS / -5.4 dBTP`** | **`0 ms`** | **`95.52%`** (up from `87.0%` before 1 ms step fix) | **`1.08×`** (`0.2–3.8 s`) | **`50.0%`** | `9f77df5a74b1` |
| **Cooking `topic-4` (`s7-7`, `--min-clip-seconds 28`)** | `33.08 s` → `30.86 s` → **`29.56 s`** (`-1,296 ms` extra dead air cut) | `1` (`0.65 s` `'بەجێی'`) → **`0`** | `0` → **`2`** | `3` (`ڕێستۆرانتەکە`, `کاشێرەکە`, `ئۆردەری`) | **`-14.0 LUFS / -4.1 dBTP`** | **`0 ms`** | **`91.22%`** (up from V6 `90.97%` & V4 `88.55%`) | **`1.15×`** (`0.4–2.2 s`) | **`50.0%`** | `6b5fcf8eb7be` |

---

## Direct Frame-by-Frame Visual Inspection Proof (`1080×1920` PNGs)

1. **`ai-v7` `s86-87`** (`D:\HawEdit-media\reels\run-2026-11-21-ai-v7\frames_v7\s86-87\`):
   - `01_hook_0p2s.png`: Balanced 2-line Studio-Gold hook card relocated onto chest (zero face overlap) + repaired `ئێستا بۆچی ئەزانی` (from `ئەگەزانی`) with `0.00 px` ghosting.
   - `02_callout_9.3s.png`: Electric-Lime contextual kinetic callout card `کەسێک توانی` in clear top headroom (`y=155`) + repaired `توانی ڕیستریکت` (from `ڕیستیک`) + `15.6%` top gold bar.
   - `04_mid_29.7s.png`: Exact `50.0%` animated top Studio-Gold progress bar + crisp filmic vignette + gold sweep on `ئەسڵەن نامەوێ`.
2. **`ai-v7` `s19-22` (`--condense --cold-open`)** (`D:\HawEdit-media\reels\run-2026-11-21-ai-v7\frames_v7\s19-22\`):
   - `01_hook_0p2s.png`: Instant cold-open climax `ژیرە دەستکردانە` right at `0.2 s` with Electric-Lime pop + balanced 2-line Studio-Gold hook card cleanly below face.
   - `02_callout_17.8s.png`: Electric-Lime contextual callout card `ئەجنەبی کوردەکان` in clear top headroom (`y=155`) + bottom karaoke `تێبگەن لە نووسراوی` + `40.0%` top gold bar.
   - `03_repaired_11.9s.png`: Repaired Sorani `لە هەرێمی کوردستان` (from `هەرمی`) with crisp gold sweep.
   - `04_mid_22.2s.png`: Exact `50.0%` animated top Studio-Gold progress bar + Electric-Lime `ناوخۆی کۆمپانیاکە کاری`.
3. **`cooking-v7` `s7-7`** (`D:\HawEdit-media\reels\run-2026-11-21-cooking-v7\frames_v7\s7-7\`):
   - `01_hook_0p2s.png`: Balanced 2-line Studio-Gold hook card in top headroom + Electric-Lime karaoke `پێش ئەوەی`.
   - `02_callout_7.9s.png`: Face-aware Electric-Lime callout card `بەجێی ناهێڵم` cleanly relocated to chest (`y=1240`) above bottom karaoke `کە دوای نانەکەمان خوار` (zero face or karaoke overlap).
   - `03_repaired_3.1s.png`: Repaired Sorani `ڕێستۆرانتەکە من بەو` (from `ڕەستۆرانتەکە`) with crisp gold sweep.
   - `04_mid_14.8s.png`: Exact `50.0%` animated top Studio-Gold progress bar + `91.22%` face share.
4. **Human verdict discipline:** `evidence/usable-rate.csv` remains header-only (`1` line; zero fabricated human verdicts).
