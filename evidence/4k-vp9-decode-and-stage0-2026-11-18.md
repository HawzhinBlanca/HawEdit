```yaml
commit: e65994019cc137d8a7e033b311c534d275832ee6
media_sha256: 6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0
host: HawaPC01 Windows-11-10.0.26300-SP0 Python-3.12.10 Dual-RTX-3090-Ti-24564MiB Driver-617.42
command: .venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4 --work-dir C:\Temp\he-remeasure-20261124\he-4k --json (and __1440p.mp4 in C:\Temp\he-remeasure-20261124\he-1440)
```

# 4K VP9 Decode & Stage 0 Ingest vs 1440p H.264 Baseline (Re-measured 2026-11-24)

Re-measured on 2026-11-24 with owner approval after the original 2026-11-18 historical commit (`1714a8b1312299fc62835bdc4bdaae7fdd30e7bf`) was absent from the recovered repository history. Every number below was freshly measured on `e65994019cc137d8a7e033b311c534d275832ee6`.

## Provenance

- **Host:** `HawaPC01`, `Windows-11-10.0.26300-SP0`
- **GPUs:** GPU `0`: `NVIDIA GeForce RTX 3090 Ti` (`24564 MiB` total, `8751 MiB` free during run); GPU `1`: `NVIDIA GeForce RTX 3090 Ti` (`24564 MiB` total, `18694 MiB` free during run); NVIDIA Driver `617.42` (`CUDA_VISIBLE_DEVICES=0`)
- **Python / packages (`.venv`):** CPython `3.12.10`, `torch 2.13.0+cpu`, `scenedetect 0.6.5`, `opencv-python-headless 4.12.0`, `silero-vad 5.1.2`, `onnxruntime 1.20.1`
- **ffmpeg:** `ffmpeg version 8.1.1-full_build-www.gyan.dev` (SHA-256 `09948d4cdd0650da6ff5a87577469f2a218dc2615ae379f8f734d24c49de0f73`)
- **Git commit:** `e65994019cc137d8a7e033b311c534d275832ee6`

## Inputs Measured

1. **4K VP9 excerpt:**
   - Path: `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4`
   - Size: `264,329,839` bytes
   - SHA-256: `6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0`
   - Measured duration: `300014` ms (`300.014 s`)
2. **Derived 1440p H.264 excerpt:**
   - Path: `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00__1440p.mp4`
   - Size: `298,767,645` bytes
   - SHA-256: `bbc2acc40bb9f69a0e1fc31b7fadc7353e628eae8acd9d69638fcda513fd95a2`
   - Measured duration: `300014` ms (`300.014 s`)

## `hawedit.pipeline` Stage 0 Ingest Comparison (`CUDA_VISIBLE_DEVICES=0`)

Commands run with `PYTHONIOENCODING=utf-8` and `HAWEDIT_MEDIA_ROOT=D:\HawEdit-media`:

- 4K run: `.venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4 --work-dir C:\Temp\he-remeasure-20261124\he-4k --json`
- 1440p run: `.venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00__1440p.mp4 --work-dir C:\Temp\he-remeasure-20261124\he-1440 --json`

| Metric | 4K VP9 (`he-4k`) | 1440p H.264 (`he-1440`) | Notes / Source Line |
|---|---:|---:|---|
| `stage0/audio.wav` size | `9,600,526` B | `9,600,526` B | `extract_audio` (`ingest.py:436`, `-threads 1` at `ingest.py:453`) |
| `stage0/proxy.mp4` size | `7,962,705` B | `7,956,545` B | `extract_proxy` (`ingest.py:486`, `-threads 1` at `ingest.py:503`) |
| **Total Stage 0 ingest (`stage_timings_s.ingest`)** | **`273.187 s` (`1.10x` RT)** | **`133.250 s` (`2.25x` RT)** | **1440p H.264 Stage 0 is `2.05x` faster** |
| Whole-CLI wall time to Stage 1 skip (exit `1`) | `274.289 s` | `134.350 s` | Stage 1 skipped without `--omni-asr` / transcript |

## Stage 0 Output Parity (4K VP9 vs 1440p H.264)

Both `stage0/ingest.json` files produced identical structural outputs:
- Identical `duration_ms`: `300014`
- Identical `shot_cuts_ms` (count `33`): `[2960, 15160, 25440, 34120, 46720, 54720, 64520, 74360, 81720, 91400, 97440, 104680, 114800, 121280, 127840, 137720, 144560, 152800, 162440, 172800, 190520, 198200, 200200, 206320, 214440, 225440, 235440, 243760, 252400, 260680, 271120, 280120, 290760]`
- Identical `speech` VAD regions: `61` regions, starting `0..382`, `866..2942`, `3202..12734`, ...

## Code Root Cause

- `src/hawedit/ingest.py:453,503` passes `"-threads", "1"` for deterministic multi-file parallel ingest, and `detect_shots` (`ingest.py:544`, called at `ingest.py:855`) runs PySceneDetect's OpenCV reader directly against `source` rather than `proxy.mp4`.
- Using the derived 1440p H.264 copy reduces Stage 0 ingest wall time by `2.05x` (`273.187 s` → `133.250 s`) while preserving exact `duration_ms`, `shot_cuts_ms`, and `speech` VAD parity.
