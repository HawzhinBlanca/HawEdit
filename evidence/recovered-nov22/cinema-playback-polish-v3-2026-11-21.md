```yaml
commit: 99e9d3e843884ada52115b8a02abe79f0d006554
media_sha256: ce05b824fb84dd1e5a1ad4e52124a4e9a9720783385c71fbaa7abe456726464c
host: HawaPC01 Windows-11-10.0.26300-SP0 Python-3.12.10 Dual-RTX-3090-Ti-24564MiB Driver-617.42
command: .venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4 --work-dir D:\HawEdit-media\reels\run-2026-11-21-ai-v3\work --output-dir D:\HawEdit-media\reels\run-2026-11-21-ai-v3 --transcript D:\HawEdit-media\reels\run-2026-11-21-ai-v3\canonical.transcript.raw.json --gemini --topic-candidates --eased-push --encoder auto --polish-captions --silence-threshold-ms 1100 --silence-target-gap-ms 300 --non-face-layout blurred_fill --judge-top-n 45 --max-clips 10 --ingest-threads 4 --json
```

# Cinema Playback Polish v3 Verification (ADR D-364, 2026-11-21)

## Provenance

- **Host:** `HawaPC01`, `Windows-11-10.0.26300-SP0`, CPython `3.12.10`, 64 CPU threads, Dual `NVIDIA GeForce RTX 3090 Ti` (`24564 MiB` each, Driver `617.42`)
- **ffmpeg:** `ffmpeg version 8.1.1-full_build-www.gyan.dev` (SHA-256 `09948d4cdd0650da6ff5a87577469f2a218dc2615ae379f8f734d24c49de0f73`), GPU 0 hardware encoder `h264_nvenc` resolved via `--encoder auto`
- **ASR:** canonical `kurdish_omniasr_7b_v12_c750.pt` + CTC-3B word alignment (`5,951` words on `ai`, `4,524` words on `cooking-30m`)
- **Editorial judge & Sorani caption polish:** `gemini-4-carbon`
- **Commits (`gemini/number-one`):**
  - `b6dfe90`: D-364 core playback polish (`step_ms=40`, `min_push_span_ms=15_000`, zero-displacement Layer 4 accent, `HOOK_EDITORIAL_THEME`, warm `SPEECH_CHAIN_FILTERS` `-18 dB / 2.2:1 / +3.5 dB` + `-5 dB` limiter, `_trim_trailing_flash_cut`, tightened narrative self-containment & Sorani ASR polish prompts)
  - `10bc778`: Studio-gold (`#FFD700`) editorial hook typography with instant crisp frame-0 opacity (`\fad(0,250)`)
  - `99e9d3e`: Luminous electric-lime (`#B8FF2E`, `&H002EFFB8&`, BT.601 luma `210 > 175`) excited karaoke accent restoring `>= 12:1` broadcast contrast (`17.27:1` measured)

---

## Direct Before vs After Playback Proof (`1553802..1610908` ms on `RO1PmSoqmCM`, 1440p)

- **Delivered v3 reel:** `D:\HawEdit-media\reels\run-2026-11-21-ai-v3\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p-topic-14.mp4` (SHA-256 prefix `cfedaa2376b8`, `reconciled=True`, `has_partial_failure=False`, `encoder=h264_nvenc`, `$1.7707`)

| Metric | `ai-c10` (`topic-14`) | `ai-v2` (`verbal-4`) | `ai-v3` (`topic-14`, `99e9d3e`) |
| --- | --- | --- | --- |
| **Even/Odd Frame-Diff Strobe Ratio** | — | `3.60×` (`2.21` vs `0.61`, 12.5 Hz sawtooth) | **`1.03×`** (`1.682` vs `1.639`, zero strobe) |
| **Trailing Camera Flash Cut (last 1.0 s)** | `122 ms` flash | `122 ms` (3-frame Speaker 1 flash) | **`0`** (`TAIL_SPIKES_LAST_1S=[]`, `out_ms` snapped `1611078 → 1610908`) |
| **Layer 4 Karaoke Ghosting (`\fscx107`)** | — | Scaled inside fixed `\clip` (double-vision ghosting) | **`0.00 px`** (`\fscx107=False`, `#B8FF2E` luminous electric lime) |
| **Median Caption Contrast Ratio** | `16.90` | `16.99` | **`17.27`** (`ink_energy_detected_share=1.0000`) |
| **Audio Loudness & Warmth (LRA)** | `-14.0 LUFS` | `-14.0 LUFS`, `LRA 2.4 LU` (over-compressed) | **`-14.0 LUFS / -6.7 dBTP / LRA 3.9 LU`** (`linear`) |
| **Hook Card Typography (Frame 0)** | Legacy `BorderStyle=3` | Jagged per-line black boxes (`BorderStyle=3`) | **Studio Gold `#FFD700`, `BorderStyle=1`**, 2-line, crisp frame 0 (`\fad(0,250)`) |
| **Face / Speaking Share** | `98.23%` | `99.29% / 99.29%` | **`99.29% / 99.29%`** |
| **Double Cuts** | `1` (`FAIL`) | `0` (`PASS`) | **`0`** (`PASS`) |
| **`BroadcastScorecard`** | **FAIL** | **PASS** | **`all_passed=True`** |

---

## Visual & Editorial Checks Across Both Genres

1. **1:1 1080p Caption Crop Inspection (`topic-14` @ `99e9d3e`):** Directly inspected zoomed 1:1 1080p crops (`لەبەر سەیفتی` and contact-sheet `چیتە دووکانێک`) — zero glyph offset, zero double-vision ghosting, crisp luminous electric-lime (`#B8FF2E`) RTL sweep inside bold white `Vazirmatn` with jet-black stroke, and `ئەزولێن → ئەجووڵێن` ASR typo polished cleanly while preserving exact CTC alignment.
2. **Frame-0 Thumbnail Inspection (`topic-14`):** Studio-gold 2-line editorial title (`لە داهاتوودا کۆمپیوتەر دەبێت / بە پارچە کاغەزێکی سەفەری`) sits cleanly across the speaker's chest at full frame-0 opacity, completely clear of eyes/forehead/beard with zero black box.
3. **Strict Self-Contained Storytelling Gate (`cooking-30m`, `run-2026-11-21-cooking-v3`, `$0.507`):** With the D-364 unresolved-pronoun self-containment rule active, `cooking-v3` cleanly returned `is_no_clip_outcome=True` (`reconciled=True`, `0` errors) — refusing the Dutch-stinginess cold-open (`بە ڕەزیلیان ناسراون` without naming the subject in the first 3 seconds) and holding the strongest conversational candidate (`verbal-5`, `fidelity=0.93`, `cultural_landing=0.90`, `risk=0.04`, `self_contained=True`) at `hook=0.74` below §2's `0.75` floor rather than padding delivery with context-dependent clips.
4. **Linear Audio Chain Benchmark (3 signals, `ffmpeg 8.1.1`):**
   - Synthetic 16 dB crest spike: `-14.15 LUFS / -6.92 dBTP / LRA 2.6 LU` (`linear`)
   - Real `ai` podcast (`1553.8s + 57.2s`): `-13.91 LUFS / -2.62 dBTP / LRA 4.9 LU` (`linear`)
   - Real hot-mic `cooking` (`1283.9s + 45.0s`): `-13.77 LUFS / -1.29 dBTP / LRA 5.1 LU` (`linear`)
