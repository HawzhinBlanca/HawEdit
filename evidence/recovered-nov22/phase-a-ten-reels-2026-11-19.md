```yaml
commit: 2ef15c04f75578f2abd62c0806ada26d27591be5
media_sha256: dff407fd45bd25eb3a1d7801c09d6a4bd3d1736ac72c52b5f8a3444e2d071b56
host: HawaPC01 Windows-11-10.0.26300-SP0 Python-3.12.10 Dual-RTX-3090-Ti-24564MiB Driver-617.42
command: .venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4 --work-dir D:\HawEdit-media\reels\run-2026-11-19-ai-10reels\work --output-dir D:\HawEdit-media\reels\run-2026-11-19-ai-10reels --topic-candidates --eased-push --judge-top-n 45 --max-clips 10 --json
```

# Phase A Real Integrated Episode Reels & Studio E2E Verification (2026-11-19 / 2026-11-20)

## Provenance

- **Host:** `HawaPC01`, `Windows-11-10.0.26300-SP0`, CPython `3.12.10`, 64 CPU threads, Dual `NVIDIA GeForce RTX 3090 Ti` (`24564 MiB` each, Driver `617.42`)
- **ffmpeg:** `ffmpeg version 8.1.1-full_build-www.gyan.dev` (SHA-256 `09948d4cdd0650da6ff5a87577469f2a218dc2615ae379f8f734d24c49de0f73`)
- **ASR checkpoint (GPU 1, `cuda:1`):** `kurdish_omniasr_7b_v12_c750.pt` (SHA-256 `f7b3a5e272e52d6c0677f78fd44c22cf6196a79a3a3057a85b7d72f759ff5fb2`) + `mms-300m` / CTC-3B forced alignment via WSL
- **Editorial judge (A5):** `gemini-4-carbon` (single-clip + C5 `GeminiPairwiseJudge`)
- **Derived 1440p input (`excerpts/`, `sources/` untouched):** `D:\HawEdit-media\excerpts\zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM__1440p.mp4` (`2,391.694 s`, `2560x1440` H.264 25 fps + Opus 48 kHz stereo, SHA-256 `dff407fd45bd25eb3a1d7801c09d6a4bd3d1736ac72c52b5f8a3444e2d071b56`; derived from 4K VP9 source `17a547016e05c1748a17ec59dc183cd7b1808387f1d7df1efdfd375cc0b1ec72` in `363.391 s`, see `evidence/a2-1440p-transcode-2026-11-19.md`)
- **Git commit (Pass 6 active-speaker wide-shot + zero-cut-flash + crisp karaoke):** `2ef15c04f75578f2abd62c0806ada26d27591be5` (`gemini/number-one`)

## Stage Wall Times (40-Minute AI Episode `RO1PmSoqmCM`)

| Stage | Cold Pass 1 (`pipeline-report-pass1-cold.json`) | Final Pass 6 (`pipeline-report.json`, Stage 0/1 cached) | Notes |
| --- | ---: | ---: | --- |
| Stage 0 (`ingest`) | `593.047 s` | `3.500 s` (cache reuse) | `2,391.694 s` 1440p H.264 |
| Stage 1 (`transcript`, WSL OmniASR v12 + CTC-3B) | `1,149.968 s` | `5.547 s` (cache reuse) | `5,951` words, `0` unaligned, `5` beam5 retries, validator disabled (D-343) |
| Stage 2 (`sentences` + `index`) | `0.047 s` | `0.125 s` | `98` sentences |
| Stage 3 (`discovery`, C1 + C4 `--topic-candidates`) | `377.688 s` | `327.578 s` | `47` candidates (`46/47` in 30–90 s target span) |
| Stage 4 (`editorial`, `gemini-4-carbon`, top 45 + C5 pairwise) | — | `38.297 s` + delivery/render | `$2.2161` across 6 reels |
| Stage 6–8 (active-speaker reframe, render via `-filter_script:v`, measure, contact sheets, export) | — | `~3,904 s` across 6 reels | Total Pass 6 wall time: `4,284.33 s` (`4,279.109 s` reported) |

### 5-Minute 1440p Excerpt Smoke (`D:\HawEdit-media\reels\smoke-2026-11-19-5m\`)

- Input: `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00__1440p.mp4`
- Stage 0: `76.2 s`; Stage 1 WSL OmniASR v12 + CTC-3B: `749` words, `0` unaligned; Stage 2: `9` sentences; Stage 3 Path A: `3` candidates; Stage 4 `gemini-4-carbon`: `22.4 s`, `$0.1017` (`50,857` tokens).
- Result: honest `0` rendered clips (`verbal-1` `self_contained=False` starting mid-conversation; `verbal-2` `109.7 s` exceeded E3 `90 s` cap due to a single 96.8 s unpunctuated sentence `[5]`).

## Delivered Reels — Pass 6 (`D:\HawEdit-media\reels\run-2026-11-19-ai-10reels\`)

- **Episode manifest (`episode.json`):** `clips_count=6`, `total_duration_ms=439682` (`439.68 s`), `total_cost_usd=2.2161`, `reconciled=true`, `has_partial_failure=false`, `is_no_clip_outcome=false` (`6` `pending-review`, `0` `failed`).
- **Why 6 reels instead of 10:** Across 45 judged candidates spanning all 40 minutes, exactly 6 distinct non-overlapping moments cleared §2's hard shippability thresholds (`MIN_HOOK_SCORE >= 0.75`, `meaning_fidelity >= 0.70`, `cultural_landing >= 0.70`, `misleading_edit_risk <= 0.10`, `self_contained=True`). Per §2 / M9.37, below-floor candidates were rejected rather than forced as filler.
- **Teaser overlap check:** Per `evidence/teaser-gold-timestamps.md`, `RO1PmSoqmCM` (`ai`) has no `"لەم پۆدکاستەدا:"` opening highlight teaser (`0.00..14.04 s` is a standalone cold-open; only `cooking` and `ep54` have opening highlight teasers), so teaser-overlap precision/recall does not apply to this episode.

| Clip | Span (s) | Dur (s) | Hook | Size (B) | Audio (LUFS / dBTP / LRA) | Face / Speaking / Y-Center | Caption Events / Contrast | Double Cuts (`<=80ms`) | MP4 SHA-256 |
| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| `verbal-1` | `2066.0–2131.0` | `65.44` | `0.82` | `26,148,318` | `-14.0 LUFS` / `-1.0 dBTP` / `4.5 LU` | `98.17%` / `98.44%` / `0.3464` | `238` / `17.26:1` | `0` (`6` cuts) | `f8dca36fb39bc8b41bb6acae5a631bd7bb1f7ac160be0b5b732a6992eca17c60` |
| `verbal-2` | `536.0–624.3` | `88.60` | `0.82` | `32,410,849` | `-14.5 LUFS` / `-0.8 dBTP` / `4.4 LU` | `98.19%` / `98.36%` / `0.3724` | `294` / `16.56:1` | `0` (`8` cuts) | `7acedd52c50969fe5f69b265ff5e848d1a803d3561527ab1eb3aaed60a84919c` |
| `verbal-3` | `1280.7–1368.3` | `87.96` | `0.78` | `34,259,724` | `-14.1 LUFS` / `-1.0 dBTP` / `4.1 LU` | `97.73%` / `97.64%` / `0.3495` | `315` / `17.10:1` | `0` (`8` cuts) | `050a0a2b9039f5c2939ae7faff99daedae23dc8f81508de1074734b4c07d5eab` |
| `verbal-6` | `2203.7–2270.9` | `67.52` | `0.78` | `27,263,859` | `-14.0 LUFS` / `-1.0 dBTP` / `6.1 LU` | `98.82%` / `98.77%` / `0.3685` | `247` / `16.54:1` | `0` (`4` cuts) | `feedd8d086de35f8fd01196412a3a09e1191be48f13e1cd54cd74b7cb910618a` |
| `verbal-9` | `777.1–828.5` | `51.68` | `0.82` | `18,971,299` | `-14.3 LUFS` / `-1.2 dBTP` / `3.8 LU` | `99.61%` / `99.60%` / `0.3771` | `171` / `17.25:1` | `0` (`4` cuts) | `341f19fdb7f6e9e086122eb003673a7064e8f9b4ea62d98b2ca3a891f2daf969` |
| `verbal-11` | `1797.6–1875.7` | `78.48` | `0.82` | `33,100,108` | `-13.8 LUFS` / `-0.9 dBTP` / `3.9 LU` | `98.47%` / `98.45%` / `0.3602` | `278` / `17.08:1` | `0` (`7` cuts) | `aa5a386745cc487c2de182c4a8687121f2a10ab771a948aa5710ec715b1e6d06` |

All 6 reels are `1080x1920`, `25.0 fps`, H.264 `yuv420p` `bt709`, AAC 48 kHz stereo, exported with sibling `.mp4.measured.json`, `.cover.png`, and `.contact-sheet.jpg` artifacts.

### Visual Contact-Sheet & Full-Timeline Verification (Pass 4 -> Pass 5 -> Pass 6)

- **Frame-exact camera cuts (`1b1a421`):** Collapsing `<= 2 ms` shot-cut steps into a zero-ramp hard switch `2 ms` before `cut_t` eliminated every 1-frame plant/carpet/half-face flash across all **37 camera cuts** in all 6 Pass 6 reels (`double_cuts=[]` on `6/6` reels).
- **Active-speaker wide-shot tracking (`2ef15c0`):** Prior to Pass 6, `OpenCvFaceTracker` locked onto the slightly larger silent host on the left during all 5 wide shots of `verbal-2` while the guest on the right spoke. Combining lower-face mouth motion (`1.57x–4.74x` higher on the speaker) with adjacent close-up HSV torso correlation (`+0.29` to `+0.59` separation) fixed **16/16 shots** across `verbal-2` (`9/9` on Speaker 2) and `verbal-1` (`7/7` on Speaker 1). Direct inspection of all 6 Pass 6 contact sheets and 16-frame 4x4 full-timeline grids of `verbal-2` and `verbal-11` confirmed centered active speakers on every wide shot and close-up.
- **Silence-capped karaoke sweeps & caption crops (`1b1a421`, `2ef15c0`):** Capping `\t(0, sweep_ms, ...)` to natural spoken word length (`400–900 ms`) eliminated 2.3–3.1 s slow-motion highlight crawls across pauses (`verbal-1` `ئەبەدەن`, `verbal-2` `لێی`). All `6/6` enlarged contact-sheet crops show crisp 128 pt Vazirmatn RTL karaoke captions (`16.54:1–17.26:1` contrast).
- **Remaining honest visual notes:** (1) On tight close-ups (`verbal-3`, `verbal-6` `FIRST 0.000s`), the golden-locked `Hook` card (`margin_v=120`, `84 pt`) sits near the speaker's forehead for `1.8 s` (modifying `HOOK_CARD_THEME` requires owner approval for `tests/golden/kurdish-hook-card.png`); (2) `--silence-threshold-ms 1000` was tested and honestly declined after E3 (`validate_edl`) caught `_identify_filler_words(detect_restarts=True)` excising Kurdish emphatic repeats (`زۆر زۆر`) with `0 ms` padding; Pass 6 preserves natural uncut conversational pacing.
- **Human watch verdicts (`evidence/usable-rate.csv`):** `0` fabricated verdicts added; awaiting owner review.

## A4 Studio Desktop E2E Verification (`hawedit.web`, Zero Flags)

- **Command:** `.venv\Scripts\python.exe -m hawedit.web --port 18765` (desktop mode, `HAWEDIT_PROTECTED_STUDIO` unset, zero pipeline flags)
- **Input slice:** `D:\HawEdit-media\reels\studio-e2e-2026-11-19\zar-ai-verbal1-75s.mp4` (`88,800,129 B`, 75 s stream-copy slice of `RO1PmSoqmCM` `2060–2135 s`, SHA-256 `89e9338d13c0c4916b262b45137e047dbe38200f941ce0ae7718c488254527f1`)
- **Report artifact:** `D:\HawEdit-media\reels\studio-e2e-2026-11-19\studio-e2e-report.json`
- **Live HTTP & SSE trace:**
  1. `GET /api/status` -> HTTP `200`, `{"status": "ready", "runner_ready": true, "active_job": null}`
  2. `POST /api/uploads` + `PUT /api/uploads/<id>` -> HTTP `201`, `source_id=02492426ccfa4817a6dc2a87ca68c749`
  3. `POST /api/repurpose` (`{"schema": 1, "source_id": "...", "options": {"preset": "viral", "max_clips": 3}}`) -> HTTP `202`, `job_id=job-1795124735895-a6a6d3b8`, `events_url=/api/jobs/job-1795124735895-a6a6d3b8/events`
  4. `GET /api/jobs/.../events` -> HTTP `200` `text/event-stream`, streamed `19` live SSE events over `376.30 s`: `ingest` (`24.5 s`), `transcript` WSL OmniASR v12 + CTC-3B (`261.8 s`), `sentences` + `index` (`0.01 s`), `discovery` (`60.7 s`), `editorial` (`28.5 s`, `$0.0501`).
  5. Honest zero-clip outcome on the 75 s standalone slice: `episode.json` recorded `clips_count=0`, `reconciled=true`, `has_partial_failure=false`, `is_no_clip_outcome=true` (`verbal-1` scored `hook=0.72 < 0.75`, `fidelity=0.88`, `cultural_landing=0.92`, `risk=0.06`, `self_contained=True` without its pre-roll lead-in). Terminal SSE event closed the stream cleanly and `GET /api/status` returned to `status="ready"`.
  6. Note: `/api/jobs/<id>/clips/<clip_id>/preview` MP4 byte-range serving was verified by automated integration test (`tests/test_a4_studio_pipeline_runner.py::test_delivered_studio_clips_serve_verified_preview_and_keep_sse_contract`); this live 75 s slice produced 0 clips so no live preview URL was emitted.
  7. Live WSL ASR health restored after run: `:8000/health` = `200`, `:8001/health` = `200` (`asr-replica-b.service` untouched).
