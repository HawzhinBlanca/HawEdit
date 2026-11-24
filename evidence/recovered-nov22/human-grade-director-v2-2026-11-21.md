```yaml
commit: 086987ea5203932bd7971bd28e8c17d7fa6ec372
media_sha256: dff407fd45bd25eb3a1d7801c09d6a4bd3d1736ac72c52b5f8a3444e2d071b56
host: HawaPC01 Windows-11-10.0.26300-SP0 Python-3.12.10 Dual-RTX-3090-Ti-24564MiB Driver-617.42
command: .venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4 --work-dir D:\HawEdit-media\reels\run-2026-11-21-ai-v2\work --output-dir D:\HawEdit-media\reels\run-2026-11-21-ai-v2 --topic-candidates --eased-push --encoder auto --polish-captions --silence-threshold-ms 1100 --silence-target-gap-ms 300 --non-face-layout blurred_fill --judge-top-n 45 --max-clips 10 --json
```

# Human-Grade Director v2 Multi-Genre Verification (2026-11-21)

## Provenance

- **Host:** `HawaPC01`, `Windows-11-10.0.26300-SP0`, CPython `3.12.10`, 64 CPU threads, Dual `NVIDIA GeForce RTX 3090 Ti` (`24564 MiB` each, Driver `617.42`)
- **ffmpeg:** `ffmpeg version 8.1.1-full_build-www.gyan.dev` (SHA-256 `09948d4cdd0650da6ff5a87577469f2a218dc2615ae379f8f734d24c49de0f73`), GPU 0 hardware encoder `h264_nvenc` resolved via `--encoder auto`
- **ASR:** canonical `kurdish_omniasr_7b_v12_c750.pt` (`f7b3a5e272e52d6c0677f78fd44c22cf6196a79a3a3057a85b7d72f759ff5fb2`) + CTC-3B word alignment
- **Editorial judge & Sorani caption polish:** `gemini-4-carbon` (single-clip + C5 pairwise + clip-only Sorani orthography & digit polish)
- **Feature commits (`gemini/number-one`):**
  - Spec & ADRs `D-360`–`D-363`: `4fea773`
  - Lane 1 (`hd-audio-cuts`, D-360 — `-2 ms` `per_shot_boxes` snap, linear broadcast speech mastering `SPEECH_CHAIN_FILTERS` + `two_pass_loudness`, `content_aware_push_schedule`): `86b346d`
  - Lane 2 (`hd-camera`, D-361 — `edge_guard_px` smooth-follow camera, per-shot zero-face cutaway motion saliency): `c24ea39`
  - Lane 3 (`hd-captions`, D-362 — face-aware 30-char 2-line hook card, zero-orphan chunk merge, acoustic karaoke micro-pop, Sorani digit normalization): `e455e79`
  - Lane 4 (`hd-integrate`, D-363 — full pipeline wiring) + VEX re-pin: `47a9be9` -> `086987e`

---

## Genre 1: 2-Person Podcast (`ai` — `RO1PmSoqmCM`, 40 min 1440p)

- **Output directory:** `D:\HawEdit-media\reels\run-2026-11-21-ai-v2\`
- **Run summary:** `reconciled=True`, `clips_count=4`, `0` delivery failures, `total_duration_ms=258,968 ms`, `encoder=h264_nvenc`, `total_cost_usd=$2.2132`, total wall `3,437.1 s` (down from `4,213.4 s` in `ai-c10`).

| Clip | Source Span (ms) | Dur (ms) | Dead Air Cut | Measured LUFS / dBTP | Loudnorm Mode (`pass2`) | Contrast | Face / Speaking Share | Double Cuts | Broadcast Scorecard | SHA-256 (prefix) |
| --- | --- | ---: | ---: | --- | --- | ---: | --- | ---: | --- | --- |
| `topic-31` | `535850..624486` | `86,400` | `2,224 ms` | `-14.0 / -2.4` | `linear` (`-13.94 / -2.65`) | `16.58` | `99.31% / 99.30%` | `0` | **PASS** | `c45be5df9728` |
| `verbal-4` | `1553802..1611078` | `56,320` | `920 ms` | `-14.0 / -4.5` | `linear` (`-14.01 / -4.72`) | `16.99` | `99.29% / 99.29%` | `0` | **PASS** | `f8ecbba57bb8` |
| `verbal-5` | `2203594..2271110` | `65,360` | `2,136 ms` | `-13.9 / -3.4` | `linear` (`-13.90 / -3.65`) | `16.78` | `99.08% / 99.07%` | `0` | **PASS** | `cc750ac2f6c5` |
| `verbal-7` | `777002..828710` | `50,800` | `888 ms` | `-13.9 / -4.2` | `linear` (`-13.90 / -4.42`) | `17.28` | `99.21% / 99.21%` | `0` | **PASS** | `4776ca8ce013` |

### Verified Before vs After Director v2 Gains (`ai-c10` -> `ai-v2`)
- **Zero double cuts (`100%`):** `1553802..1611078` (`topic-14` -> `verbal-4`) improved from `double_cuts_count=1` (`BroadcastScorecard=FAIL`) to **`double_cuts_count=0` (`BroadcastScorecard=PASS`)** via D-360 `-2 ms` `per_shot_boxes` snap; face share rose `98.23% -> 99.29%`.
- **Linear broadcast audio (`100%`):** All 4 reels converged in pure `linear` mode to `-13.9..-14.0 LUFS` (`±0.10 LU`) and `-2.4..-4.5 dBTP` (`0` loudness or true-peak failures).
- **Face-aware 2-line hook cards (`D-362`):** Visually verified on all 4 contact sheets — close-up openers (`verbal-4`, `verbal-5` `FIRST 0.000s`) automatically relocated the 2-line pill onto the speaker's chest completely off the forehead/eyes; wide-shot openers (`topic-31`, `verbal-7` `FIRST 0.000s`) kept a sleek 2-line pill in top headroom.
- **Zero-orphan captions (`D-362`):** On `535850..624486`, the `82.710 s` 1-word orphan `لێی` in `ai-c10/verbal-4` cleanly merged into `زۆر زۆر جوان لێی` (`ai-v2/topic-31` @ `82.355 s`).
- **Live intra-shot active-speaker switching (`D-357`):** Visually confirmed on `verbal-4` (`CUT #4 50.640s -> 50.680s`) and `verbal-7` (`CUT #6 44.672s -> 44.712s`).

---

## Genre 2: Dynamic Show with Human-Picked Teaser Ground Truth (`cooking-30m` — `k_jxP903t5w`, `00:00..30:07`)

- **Output directory:** `D:\HawEdit-media\reels\run-2026-11-21-cooking-v2\`
- **Run summary:** `reconciled=True`, `clips_count=2`, `0` loudness failures, `0` `MAX_PATH` errors, `encoder=h264_nvenc`, `total_cost_usd=$1.0483`, total wall `2,308.4 s`.

| Clip | Source Span (ms) | Dur (ms) | Dead Air Cut | Measured LUFS / dBTP | Loudnorm Mode (`pass2`) | Contrast | Face / Speaking Share | Double Cuts | Teaser Hit | SHA-256 (prefix) |
| --- | --- | ---: | ---: | --- | --- | ---: | --- | ---: | --- | --- |
| `verbal-3` | `373578..450118` | `75,600` | `920 ms` | `-14.0 / -1.1` | `linear` (`-13.96 / -1.35`) | `14.48` | `83.07% / 83.02%` | `0` | **G03 (`1.78 s`)** | `dd5ae57b0b88` |
| `verbal-5` | `548330..614822` | `66,480` | `0 ms` | `-14.0 / -1.3` | `linear` (`-13.91 / -1.54`) | `17.14` | `92.79% / 92.68%` | `0` | — | `2c66fe5a3bc1` |

### Visual Contact-Sheet Inspection (`cooking-v2`)
- **Linear audio mastering cured high-crest cooking audio:** Both `verbal-3` and `verbal-5` achieved exact `-14.0 LUFS` (`-1.1 / -1.3 dBTP`, `normalization_type='linear'`), vs `-14.7..-14.8 LUFS` failures prior to D-360.
- **Both face-aware hook card branches confirmed visually:** `verbal-3` (`FIRST 0.000s`, close-up) relocated off the face onto the chest; `verbal-5` (`FIRST 0.000s`, wide shot) rendered a crisp 2-line wide pill in top headroom.
- **Per-shot zero-face cutaway framing (`D-361`):** On `verbal-3` (`CUT #5`, `#7`, `#8`), zero-face hand-gesture cutaways over the table were centered via motion saliency with `0` double cuts across all 12 cuts (`verbal-5` also improved `92.19% -> 92.79%` face share and `16.80 -> 17.14` contrast, `BroadcastScorecard=PASS`).
- **Honest fail-stop note:** `verbal-1` halted cleanly on `face_tracking_unsubstantiated: 72.43% < 80%` (strict fail-stop respected); `verbal-3` passed delivery under `--min-face-share 0.80` (`83.07%`), while `BroadcastScorecard`'s fixed `90%` podcast face-share flag honestly recorded `face_framing_ok=False` due to the genuine zero-face hand cutaway shots.
