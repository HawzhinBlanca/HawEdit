```yaml
commit: 1714a8b1312299fc62835bdc4bdaae7fdd30e7bf
media_sha256: 6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0
host: HawaPC01 Windows-11-10.0.26300-SP0 Python-3.12.10 Dual-RTX-3090-Ti-24564MiB Driver-617.42
command: .venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4 --work-dir C:\Temp\he-a2-4k (and __1440p.mp4 in C:\Temp\he-a2-1440)
```

# 4K VP9 Decode & Stage 0 Ingest vs 1440p H.264 Baseline (2026-11-18)

## Provenance

- **Host:** `HawaPC01`, `Windows-11-10.0.26300-SP0`
- **GPUs:** GPU `0`: `NVIDIA GeForce RTX 3090 Ti` (`24564 MiB` total, `6256 MiB` free during audit); GPU `1`: `NVIDIA GeForce RTX 3090 Ti` (`24564 MiB` total, `7849 MiB` free during audit); NVIDIA Driver `617.42` (`CUDA_VISIBLE_DEVICES=0`)
- **Python / packages (`.venv`):** CPython `3.12.10`, `torch 2.13.0+cpu` (`cuda False`), `scenedetect 0.6.5`, `opencv-python-headless 4.12.0.88`, `silero-vad 5.1.2`, `onnxruntime 1.20.1`
- **ffmpeg:** `ffmpeg version 8.1.1-full_build-www.gyan.dev` (SHA-256 `09948d4cdd0650da6ff5a87577469f2a218dc2615ae379f8f734d24c49de0f73`)
- **Git commit:** `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf`

## Inputs Measured

1. **4K VP9 excerpt (existing baseline):**
   - Path: `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4`
   - Size: `264,329,839` bytes
   - SHA-256: `6f784e239a371306313882d3377906eb6d3d0afd3927804dc37c68d567aaf4e0`
   - `ffprobe` streams: `vp9` `3840x2160`, `25/1` fps, `7571` frames; `opus` `48000 Hz`, `2` ch, `15144` frames; duration `300.014000 s`
2. **Derived 1440p H.264 excerpt (created in `D:\HawEdit-media\excerpts\`, GPU 0 NVENC, `D:\HawEdit-media\sources\` untouched):**
   - Command (`CUDA_VISIBLE_DEVICES=0`): `ffmpeg -y -hwaccel cuda -i D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4 -vf scale=2560:1440 -c:v h264_nvenc -preset p6 -rc vbr -cq 18 -b:v 0 -c:a copy D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00__1440p.mp4`
   - Transcode wall time: `47.915 s`
   - Path: `D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00__1440p.mp4`
   - Size: `298,767,645` bytes
   - SHA-256: `bbc2acc40bb9f69a0e1fc31b7fadc7353e628eae8acd9d69638fcda513fd95a2`
   - `ffprobe` streams: `h264` `2560x1440`, `25/1` fps, `7500` frames; `opus` `48000 Hz`, `2` ch, `15051` frames; duration `300.014000 s`

## Standalone FFmpeg Video Decode Throughput (300.014 s Excerpt)

| Input | Mode | Wall Time (s) | Speed vs Real Time |
|---|---|---|---|
| 4K VP9 (`3840x2160`) | `-threads 1` (CPU null sink) | `168.545` | `1.78x` |
| 4K VP9 (`3840x2160`) | default threads (CPU null sink) | `46.965` | `6.39x` |
| 4K VP9 (`3840x2160`) | `-hwaccel cuda` (GPU 0 null sink) | `24.271` | `12.36x` |
| 1440p H.264 (`2560x1440`) | `-threads 1` (CPU null sink) | `66.824` | `4.49x` |
| 1440p H.264 (`2560x1440`) | default threads (CPU null sink) | `9.403` | `31.91x` |
| 1440p H.264 (`2560x1440`) | `-hwaccel cuda` (GPU 0 null sink) | `15.715` | `19.09x` |

Note: on 1440p H.264, multi-threaded CPU decode (`9.403 s`) outran CUDA decode (`15.715 s`) on Threadripper + NVDEC. On 4K VP9, `-threads 1` decode (`168.545 s`) is `3.59x` slower than default-threaded CPU decode (`46.965 s`) and `6.94x` slower than `-hwaccel cuda` (`24.271 s`).

## `hawedit.pipeline` Stage 0 Ingest Sub-Step Breakdown (`CUDA_VISIBLE_DEVICES=0`)

Commands run with `PYTHONIOENCODING=utf-8` and `HAWEDIT_MEDIA_ROOT=D:\HawEdit-media`:

- 4K run: `.venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4 --work-dir C:\Temp\he-a2-4k --json`
- 1440p run: `.venv\Scripts\python.exe -m hawedit.pipeline D:\HawEdit-media\excerpts\zar-ai-lamo__RO1PmSoqmCM__05m00-10m00__1440p.mp4 --work-dir C:\Temp\he-a2-1440 --json`

| Sub-step | 4K VP9 (`C:\Temp\he-a2-4k`) | 1440p H.264 (`C:\Temp\he-a2-1440`) | Notes / Source Line |
|---|---:|---:|---|
| `sha256` + `extract_audio` (`audio.wav`, `9,600,526` B) | `12.825 s` | `12.243 s` | Audio is 48 kHz Opus in both (`ingest.py:430-455`) |
| `extract_proxy` (`proxy.mp4`) | `160.529 s` (`7,962,705` B) | `63.952 s` (`7,956,545` B) | Hardcodes `-threads 1` (`ingest.py:493`) |
| `probe` + `detect_speech` + `detect_shots` + `save` | `167.987 s` | `60.359 s` | `probe_duration_ms=0.356 s`, `detect_speech=6.877 s` (61 regions), remainder OpenCV `detect_shots` (`ingest.py:534`) |
| **Total Stage 0 ingest (`ingest.json`)** | **`341.341 s` (`0.88x` RT)** | **`136.554 s` (`2.20x` RT)** | **4K VP9 Stage 0 runs slower than real time** |
| Whole-CLI wall time to Stage 1 skip (exit `1`) | `342.235 s` | `137.054 s` | Stage 2 extracted `34` visual windows / `315` frames (`1.0 fps`), Stage 1 skipped |

## Stage 0 Output Parity (4K VP9 vs 1440p H.264)

Both `C:\Temp\he-a2-4k\run1_stdout.json` and `C:\Temp\he-a2-1440\run1_stdout.json` produced:
- Identical `duration_ms`: `300014`
- Identical `shot_cuts_ms` (count `33`): `[2960, 15160, 25440, 34120, 46720, 54720, 64520, 74360, 81720, 91400, 97440, 104680, 114800, 121280, 127840, 137720, 144560, 152800, 162440, 172800, 190520, 198200, 200200, 206320, 214440, 225440, 235440, 243760, 252400, 260680, 271120, 280120, 290760]`
- Identical `speech` VAD regions: `61` regions, starting `0..382`, `866..2942`, `3202..12734`, ...

## Code Root Cause & Linear Cost Extrapolation (Not Measured on Full Episodes)

- `src/hawedit/ingest.py:445,493` deliberately passes `"-threads", "1"` (documented in module header lines 10–11 as optimizing multi-file parallel ingest), and `detect_shots` (`ingest.py:534`) runs PySceneDetect's single-process OpenCV video reader directly on `source` rather than on `proxy.mp4` or hardware-accelerated frames.
- **Unmeasured linear scaling extrapolation** from the 300.014 s excerpt (for capacity planning only; actual full-episode timings must be measured once run):
  - 40 min (`zar-ai-half-episode-lamo`, `39:52`): ~45 min at current 4K VP9 vs ~18 min at current 1440p H.264 (`-threads 1`).
  - 1h08 (`zar-mjewr-cooking`, `1:07:42`): ~77 min 4K VP9 vs ~31 min 1440p H.264.
  - 1h48 (`zar-ep54-younis-gardwni-cosmos`, `1:47:41`): ~123 min 4K VP9 vs ~49 min 1440p H.264.
- Deriving 1440p H.264 copies in `D:\HawEdit-media\excerpts\` cuts Stage 0 runtime by `2.50x` today without altering `shot_cuts_ms` or VAD regions; removing the `-threads 1` bottleneck in `extract_proxy` and reading `proxy.mp4` / fast decode in `detect_shots` reduces single-episode wall time further.
