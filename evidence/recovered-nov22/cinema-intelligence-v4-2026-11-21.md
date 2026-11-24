```yaml
commit: c2f5875ff952d4a5864e761dfd921f7063dd9366
media_sha256: ce05b824fb84dd1e5a1ad4e52124a4e9a9720783385c71fbaa7abe456726464c
host: HawaPC01 Windows-11-10.0.26300-SP0 Python-3.12.10 Dual-RTX-3090-Ti-24564MiB Driver-617.42
command: .venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4 --work-dir D:\HawEdit-media\reels\run-2026-11-21-ai-v4\work --output-dir D:\HawEdit-media\reels\run-2026-11-21-ai-v4 --transcript D:\HawEdit-media\reels\run-2026-11-21-ai-v4\canonical.transcript.raw.json --gemini --topic-candidates --eased-push --encoder auto --polish-captions --silence-threshold-ms 1100 --silence-target-gap-ms 300 --non-face-layout blurred_fill --judge-top-n 45 --max-clips 10 --ingest-threads 4 --json
```

# Cinema Intelligence v4 Multi-Genre Verification (ADRs D-365–D-368, 2026-11-21)

## Provenance

- **Host:** `HawaPC01`, `Windows-11-10.0.26300-SP0`, CPython `3.12.10`, 64 CPU threads, Dual `NVIDIA GeForce RTX 3090 Ti` (`24564 MiB` each, Driver `617.42`)
- **ffmpeg:** `ffmpeg version 8.1.1-full_build-www.gyan.dev` (SHA-256 `09948d4cdd0650da6ff5a87577469f2a218dc2615ae379f8f734d24c49de0f73`), GPU 0 hardware encoder `h264_nvenc` resolved via `--encoder auto`
- **ASR:** canonical allowlisted `kurdish_omniasr_7b_v12_c750.pt` + CTC-3B word alignment (`5,951` words on `ai`, `4,524` words on `cooking-30m`)
- **Editorial judge & Sorani caption polish:** `gemini-4-carbon`
- **Commit (`gemini/number-one`):** `c2f5875ff952d4a5864e761dfd921f7063dd9366` implementing `D-365` (word-level acoustic peak + payoff highlight rhythm), `D-366` (Kurdish syntactic phrase rebalancing + function-word stutter cleanup), `D-367` (`300 s` Path A HTTP timeout + hook-first opener guidance), and `D-368` (`15 ms / 60 ms` quadratic-sine broadcast loop audio micro-fades)

---

## Multi-Genre Delivered v4 Reels (`h264_nvenc`, `reconciled=True`, `0` Path A Timeouts)

### Genre 1: 2-Person Tech Podcast (`ai-v4` — `RO1PmSoqmCM`, 40 min 1440p)
- **Output directory:** `D:\HawEdit-media\reels\run-2026-11-21-ai-v4\`
- **Run summary:** `Path A discovery = 364.8 s (OK, 0 timeouts)`, `clips_count=2`, `reconciled=True`, `has_partial_failure=False`, `total_cost_usd=$2.1997`, `encoder=h264_nvenc`

### Genre 2: Dynamic Multi-Cam Cooking Show (`cooking-v4` — `k_jxP903t5w`, `00:00..30:07` 1440p)
- **Output directory:** `D:\HawEdit-media\reels\run-2026-11-21-cooking-v4\`
- **Run summary:** `Path A discovery = 287.6 s (OK, 0 timeouts)`, `clips_count=1`, `reconciled=True`, `total_cost_usd=$1.6093`, `encoder=h264_nvenc`

| Reel | Genre | Dur (s) | Strobe Ratio | Tail Flashes | Double Cuts | Audio (LUFS / dBTP) | Contrast (`ink_share`) | Acoustic Rhythm (Gold / Lime) | 1-Word Orphans | Face / Speaking Share | Scorecard | SHA-256 (prefix) |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | --- | --- | --- |
| `ai-v4/verbal-2` | Podcast | `86.40` | `1.10×` | `0` | `0` | `-14.0 / -4.9` | `15.12` (`1.0000`) | `71.0% / 29.0%` | `0 / 77` | `98.84% / 98.83%` | **ALL PASS** | `e5cae6e104de` |
| `ai-v4/verbal-3` | Podcast | `65.36` | `1.05×` | `0` | `0` | `-13.9 / -5.6` | `16.31` (`1.0000`) | `72.0% / 28.0%` | `0 / 64` | `99.39% / 99.38%` | **ALL PASS** | `17f308a4d954` |
| `cooking-v4/topic-4` | Dynamic Show | `33.08` | `1.02×` | `0` | `0` | `-14.0 / -3.8` | `14.35` (`1.0000`) | `64.8% / 35.2%` | `0 / 41` | `88.55% / 89.09%` | `0` dbl cuts / loudness / contrast PASS | `57be3fd99af7` |

---

## Visual & Linguistic Verification Highlights

1. **Dual-Color Word-Level Acoustic Rhythm (`D-365`):** Direct 1:1 1080p caption crops (`ai_1440p-verbal-3_gold_1to1.png` `زۆر قووڵ ئەڕوات`, `ai_1440p-verbal-3_lime_1to1.png` `ئەمانە بۆیە گەورەترین`, `cook_1440p-topic-4_{gold,lime}_1to1.png`) visually confirmed zero ghosting (`0.00 px`) and live mid-phrase contrast where vocal-peak words (`زۆر`, `گەورەترین`) ignite in luminous electric lime (`#B8FF2E`) while surrounding calm words sweep in Studio Gold (`#FFE500`) — eliminating `ai-v3`'s `100.0%` monotone lime saturation.
2. **Kurdish Syntactic Phrase Chunking & Emphatic Preservation (`D-366`):** `0 / 182` stranded 1-word popups across all three reels, `0` `وەکو وەکو` function-word stutters, and `100%` preservation of intentional Kurdish emphatic repeats (`زۆر زۆر جوان لێی`, `زۆر زۆر گەورە`, `زۆر زۆر حەز`).
3. **Editorial Frame-0 Hook Typography (`D-364`):** Visually verified on all three frame-0 renders — crisp studio-gold (`#FFD700`) `BorderStyle=1` typography positioned in top headroom on wide shots (`ai-v4/verbal-2`, `cooking-v4/topic-4`) and relocated cleanly off forehead onto chest on close-ups (`ai-v4/verbal-3`).
4. **Honest Fail-Stop Check (Unseen 3rd Genre `ep54-cosmos`):** Attempting live Stage 1 transcription on `zar-ep54-cosmos__xMEcurfWjic__05m00-17m00.mp4` halted loudly at `ChampionUnavailable` because `/mnt/f/.../kurdish_omniasr_7b_v12_c750.pt` hashed to `c6a22837...` instead of the allowlisted `f7b3a5e2...`, confirming zero silent fallback on unverified model weights.
