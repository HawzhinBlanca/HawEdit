```yaml
commit: 2b5d6a72c1c85936f22171d1fd336e3df6744b76
media_sha256: dff407fd45bd25eb3a1d7801c09d6a4bd3d1736ac72c52b5f8a3444e2d071b56
host: HawaPC01 Windows-11-10.0.26300-SP0 Python-3.12.10 Dual-RTX-3090-Ti-24564MiB Driver-617.42
command: .venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4 --work-dir D:\HawEdit-media\reels\run-2026-11-20-ai-c10\work --output-dir D:\HawEdit-media\reels\run-2026-11-20-ai-c10 --topic-candidates --eased-push --encoder auto --polish-captions --silence-threshold-ms 1100 --silence-target-gap-ms 300 --non-face-layout blurred_fill --judge-top-n 45 --max-clips 10 --json
```

# Content-Aware 10/10 Multi-Genre Production Verification (2026-11-20)

## Provenance

- **Host:** `HawaPC01`, `Windows-11-10.0.26300-SP0`, CPython `3.12.10`, 64 CPU threads, Dual `NVIDIA GeForce RTX 3090 Ti` (`24564 MiB` each, Driver `617.42`)
- **ffmpeg:** `ffmpeg version 8.1.1-full_build-www.gyan.dev` (SHA-256 `09948d4cdd0650da6ff5a87577469f2a218dc2615ae379f8f734d24c49de0f73`), GPU 0 hardware encoder `h264_nvenc` resolved via `--encoder auto`
- **ASR checkpoint (GPU 1, `cuda:1`):** `kurdish_omniasr_7b_v12_c750.pt` (SHA-256 `f7b3a5e272e52d6c0677f78fd44c22cf6196a79a3a3057a85b7d72f759ff5fb2`) + CTC-3B forced alignment via WSL2
- **Editorial judge & Sorani caption polish:** `gemini-4-carbon` (single-clip + C5 pairwise + clip-only Sorani orthography polish with strict CTC timestamp preservation)
- **Feature commits (`gemini/number-one`):**
  - Spec & ADRs `D-356`–`D-359`: `10e904c`
  - Lane A (`c10-discovery` — `audio_signals.py`, Path A acoustic tags, C4 boost, teaser overlap): `dc01828`
  - Lane B (`c10-reframe` — downscaled Haar, intra-shot rolling-window active speaker, motion tracking, `resolve_encoder`): `6c39bb1`
  - Lane C (`c10-captions` — stutter dedup, Sorani caption polish, E3-safe silence tightening): `6edd0b2`
  - Lane D (`c10-integrate` — pipeline wiring, `BroadcastScorecard`): `23107d8`
  - Live-run production fixes: `a3c2509` (frame before silence trim, tightened episode duration reconciliation, K-run Path A voting resilience), `b804336` (`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` + `>20 s` OOM half-split), `2b5d6a7` (short contact-sheet temp filename avoiding Windows `MAX_PATH`)

---

## Genre 1: 2-Person Podcast — `ai` (`RO1PmSoqmCM`, 40 min 1440p)

- **Input:** `D:\HawEdit-media\excerpts\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4` (`2,391.694 s`, SHA-256 `dff407fd45bd25eb3a1d7801c09d6a4bd3d1736ac72c52b5f8a3444e2d071b56`, `sources/` untouched)
- **Output directory:** `D:\HawEdit-media\reels\run-2026-11-20-ai-c10\`
- **Run summary:** `reconciled=True`, `clips_count=5`, `total_duration_ms=346,070 ms`, `encoder=h264_nvenc`, `total_cost_usd=$2.2230`, `stage_timings_s`: ingest `590.156 s` (reuse `1.703 s`), transcript `5.469 s` (cache), sentences `0.093 s`, discovery `329.672 s`, editorial `86.907 s`, total `4,213.39 s`.
- **Honest fail-stop rejection:** `verbal-1` halted cleanly at `verify_delivery` with `true_peak_violation: expected '<= -0.7', measured -0.6` under single-pass default profile (`--profile default`). Zero silent fallbacks.

| Clip | Source Span (ms) | Rendered Dur (ms) | Silence Excised (ms) | LUFS / dBTP | Contrast | Face / Speaking Share | Double Cuts | Broadcast Scorecard | SHA-256 (prefix) | Title (ckb) |
| --- | --- | ---: | ---: | --- | ---: | --- | ---: | --- | --- | --- |
| `verbal-4` | `535850..624486` | `86,400` | `2,224` | `-14.5 / -0.9` | `15.43` | `98.84% / 98.83%` | `0` | `PASS` | `4058cb820069` | ژیریی دەستکرد لە کوردستان جێگەی کام پیشەیە دەگرێتەوە؟ |
| `verbal-3` | `1280560..1368486` | `87,120` | `824` | `-14.1 / -1.0` | `17.03` | `97.48% / 97.40%` | `0` | `PASS` | `1b6d1ea0ede9` | چۆن لە سەردەمی پلەیستەیشن و سیدیدا بە ئینتەرنێت پارەم پەیدا دەکرد؟ |
| `verbal-2` | `777002..828710` | `50,800` | `888` | `-14.3 / -1.2` | `17.30` | `99.61% / 99.60%` | `0` | `PASS` | `d7e707b72157` | ئایا زیرەکیی دەستکرد جێگەی مرۆڤ دەگرێتەوە؟ |
| `topic-14` | `1553802..1611078` | `56,320` | `920` | `-14.1 / -1.5` | `17.10` | `98.23% / 98.21%` | `1` | `FAIL (1 rapid cut @ 56.1s)` | `24ad8704f8f9` | لە داهاتوودا کۆمپیوتەر دەبێتە پارچە کاغەزێکی سەفەری! |
| `verbal-9` | `2203594..2271110` | `65,360` | `2,136` | `-14.0 / -0.9` | `16.81` | `99.39% / 99.38%` | `0` | `PASS` | `1cdfd80f3f47` | بۆچی لابردنی سنوورەکانی ژیریی دەستکرد مەترسیدارە؟ |

### Pixel-Verified Zero-Flash Silence-Trim Fix (`a3c2509`)

On the identical span `535,850..624,486 ms` (`2,224 ms` silence excised) around Cut #1 (`7,880 ms`):
- **Before `a3c2509` (`topic-31`, crop after `silence_trim_filter`):** `frame 196 (7840ms) diff=0.3 -> frame 197 (7880ms) diff=68.2 -> frame 198 (7920ms) diff=48.8 -> frame 199 (7960ms) diff=1.6` (1-frame half-face flash caused by `setpts=PTS-STARTPTS` shifting frames earlier by `30 ms` relative to `crop_filter`).
- **After `a3c2509` (`verbal-4`, crop before `silence_trim_filter`):** `frame 196 (7840ms) diff=0.3 -> frame 197 (7880ms) diff=59.8 -> frame 198 (7920ms) diff=1.6 -> frame 199 (7960ms) diff=1.6` (**zero** 1-frame double-cut flash).

### Visual Contact-Sheet Inspection (`ai-c10`)

All 5 `.contact-sheet.jpg` sheets were visually inspected frame-by-frame:
- `verbal-4`, `verbal-2`, `verbal-9`: spotless across every cut tile (`FIRST` through final `POST`); zero carpet/half-face flashes; upper-third eye framing; crisp RTL Sorani karaoke captions (`15.43–17.30:1` contrast).
- Live intra-shot active-speaker switches (`D-357`) visually confirmed mid-wide-shot on `verbal-2` (`CUT #6 44.672s -> 44.712s`), `topic-14` (`CUT #4 50.640s -> 50.680s`), and `verbal-3` (`CUT #1, #2, #5, #6, #7`).
- Honest defect notes: on `verbal-3` `CUT #4 PRE 29.320s`, the right speaker leans toward frame edge immediately before cutting to the left speaker; on `topic-14`, `BroadcastScorecard` flagged `double_cuts_count=1` near `56.1s` (end of clip).

---

## Genre 2: Dynamic Show with Human-Picked Teaser Ground Truth — `cooking` (`k_jxP903t5w`)

- **Full-episode 1440p derivation (`excerpts/`, `sources/` untouched):** `D:\HawEdit-media\excerpts\zar-mjewr-cooking-with-hawzhin-2026-10-26__k_jxP903t5w__1440p.mp4` (`4,062 s`, `4,692,021,008 B`, SHA-256 `21bddc9c1b7487a40da447f405fd95020f2a782421b4a6b592e5053c31b36c4e`, GPU 0 NVENC transcode `610.18 s` = `6.66x` real time).
- **Honest full-episode Stage 1 findings (strict fail-stop):**
  1. Continuous `37.968 s` opening music+speech teaser (`speech-0000.wav`) initially triggered CUDA OOM (`21.70 GiB` allocated + `1.45 GiB` reserved unallocated on RTX 3090 Ti 24 GiB). Fixed cleanly in `b804336` (`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` + `>20 s` OOM half-split into contiguous halves).
  2. With `b804336`, Stage 1 transcribed **126 consecutive segments (`0..1,806.718 s`, 30.1 min, 4,524 Sorani words, 133 checkpoint ops)** before halting honestly under `D-278` strict fail-stop at `30:15` (`speech-0126-sub-02.wav`, `1,815,650..1,824,350 ms`, `DecodeIncomplete`: greedy no natural EOS + beam-5 4x repetition loop).
- **30-Minute Excerpt Production Run (`00:00..30:07`, 11 of 17 verified gold teaser spans):**
  - Input: `D:\HawEdit-media\excerpts\zar-mjewr-cooking-with-hawzhin-2026-10-26__k_jxP903t5w__00m00-30m07__1440p.mp4` (`1,807.0 s`, SHA-256 `28c1aa3475a7d4eabf01614a4419a2b14517f16a258dfab8bf0d253c42834168`), stream-copied (`-c copy`) with canonical OmniASR v12 + CTC-3B transcript (`4,524` words, `2..1,806,718 ms`).
  - Output directory: `D:\HawEdit-media\reels\run-2026-11-20-cooking-30m-c10\`

### Teaser-Overlap Benchmark (`evaluate_teaser_overlap` vs `evidence/teaser-gold-timestamps.md`)

Evaluated against all **11** verified human-editor gold teaser source spans falling inside `0..1,807 s` (`G02, G03, G04, G05, G06, G09, G10, G14, G15, G16, G17`, `min_overlap_ms=1500`):
- **Stage 3 Multimodal Discovery (36 candidates — acoustic `audio_signals.py` + Path A + C4 `--topic-candidates`):**
  - **Hits:** **`10 / 11`** (`G03` `14.48 s`, `G04` `4.61 s`, `G05` `16.42 s`, `G06` `15.44 s`, `G09` `6.72 s`, `G10` `21.15 s`, `G14` `14.52 s`, `G15` `6.40 s`, `G16` `7.88 s`, `G17` `6.24 s`; missed `G02`)
  - **Recall:** **`90.91%`** (`0.9091`) | **Precision:** **`44.44%`** (`0.4444`) | **F1:** **`0.5970`**
- **Stage 4 Editorial-Passed Set (Run 1, 3 clips: `verbal-1`, `verbal-5`, `verbal-8`):**
  - **Hits:** `3 / 11` (`G05` `8.85 s`, `G15` `6.40 s`, `G16` `7.88 s`) | **Precision:** **`66.67%`** (`0.6667`) | **Recall:** **`27.27%`** (`0.2727`) | **F1:** **`0.3871`**

### Delivered Reel & Production Diagnostics (`cooking-30m`)

- **`cooking-verbal-2`** (`D:\HawEdit-media\reels\run-2026-11-20-cooking-30m-c10\cooking-verbal-2.mp4`, SHA-256 `f2c4178eca0aabfd5a5d545fdf07d6be16012418a35bd027d14d4cbad5b550f6`, span `548,330..614,822 ms`, `66,480 ms`, title: *نهێنی نووسینی تکایە وێر نییە لە ڕێستۆرانتەکاندا*):
  - **Passed all delivery gates & `BroadcastScorecard`:** `-14.5 LUFS / -0.8 dBTP`, contrast `16.80:1`, face share `92.19%` (`speaking_face_share=92.07%`, `median_y_center=33.75%`), `0` double cuts across 10 camera cuts, `all_passed=True`.
  - **Contact sheet (`cooking-verbal-2.contact-sheet.jpg`, SHA-256 `2c3afd11cf3a`):** visually inspected across all 21 tiles — crisp RTL Sorani captions (`چییە ئەی هاوار`, `خۆتان بە عەقڵی`), zero double-cut flashes; honest note: on `CUT #3 POST 16.510s` the speaker leans far left briefly before centering cleanly on `CUT #4`.
  - **Windows `MAX_PATH` bug caught & fixed (`2b5d6a7`):** post-publish contact sheet temp file (`.zar-mjewr-...contact-sheet.jpg.<pid>.tmp`) reached `263` chars (`>260`), fixed to `.cs-<pid>.tmp`.
- **Honest fail-stop rejections on `cooking-30m`:** `verbal-8` (`loudness_violation: measured -14.7 LUFS vs -14.0 ± 0.5`), `verbal-9` (`face_tracking_unsubstantiated: 71.16% < 80%`).
