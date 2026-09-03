# Research — Deliverable Encode Profile (Task T2.10)

> Measured 2026-09-03 on `HAWAPC01` (Windows 11 Pro, AMD Ryzen Threadripper 3990X 64-Core, 256 GB RAM, 2× NVIDIA GeForce RTX 3090 Ti 24 GB).
> ffmpeg 8.1.1-full_build-www.gyan.dev (libass, HarfBuzz, FriBidi, NVENC, libvmaf).

## 1. Problem Statement & Background

In `specs/pro-grade-program/research.md` §4.1:
- Current render configuration in `src/hawedit/render.py`:
  - Encoders: `h264_nvenc -rc vbr -cq 20 -b:v 0` or `libx264 -crf 20`.
  - Missing tuning: No preset, profile (`high`), B-frame tuning (`-bf 3`), adaptive quantization (`-spatial-aq 1 -temporal-aq 1`), GOP structure (`-g 2*fps`), or standard broadcast color tags (`bt709`).
  - Scaling filter: Default bicubic `scale=1080:1920` without Lanczos sharpening or unsharp filtering.
  - Decode throttling: Hardcoded `-threads 1` on decode input stream slows down multicore systems unnecessarily.
  - Bitrate: Delivered clips come out at ~2.79 Mbps, resulting in noticeable compression softening on fine text and facial details.
  - Working renders currently share the same profile without a distinction between fast working renders (`-cq 27` / `-crf 27`) and pristine broadcast delivery (`-cq 20` / `-crf 20`).

Task T2.10 in `specs/pro-grade-program/tasks.md` specifies:
> **Deliverable encode profile.** NVENC `-preset p6 -profile high -bf 3 -spatial-aq 1 -temporal-aq 1 -cq 20 -g 2×fps`, colour tags `bt709`, lanczos scale + light `unsharp`, remove `-threads 1` from decode; libx264 equivalent (`-preset slow -profile:v high -bf 3 -crf 20 -g 2×fps`). Working renders keep `-cq 27`. Target 8–12 Mbps at 1080×1920.

## 2. Hardware & Encoding Capabilities on HAWAPC01

Probing `ffmpeg 8.1.1` on `HAWAPC01` confirms:
1. `h264_nvenc`:
   - `-preset p6` (High quality single-pass / 2-pass equivalent on Ampere).
   - `-profile:v high` (H.264 High Profile).
   - `-bf 3` (3 bidirectional B-frames for temporal compression efficiency).
   - `-spatial-aq 1 -temporal-aq 1` (Spatial and temporal adaptive quantization).
   - `-rc vbr -cq 20 -b:v 0` (Variable bitrate with constant quality index 20, unconstrained upper limit).
   - `-g <2*fps>` (2-second closed keyframe GOP for clean seeking and streaming).
2. `libx264`:
   - `-preset slow` (optimal rate-distortion optimization).
   - `-profile:v high`.
   - `-bf 3`.
   - `-crf 20`.
   - `-g <2*fps>`.
3. Color Tags:
   - `-color_primaries bt709 -color_trc bt709 -colorspace bt709` (matches standard sRGB/Rec.709 displays and social platforms without color shift).
4. Video Filters:
   - Lanczos scaling: `scale={target_width}:{target_height}:flags=lanczos`
   - Light unsharp: `unsharp=5:5:0.5:5:5:0.0` (subtle luma sharpening to restore edge contrast after vertical crop upscaling, 0 chroma sharpening to avoid chroma noise).
5. Multi-threaded Decode:
   - Omission of `-threads 1` on the input flags allows ffmpeg to autothread decoding based on host CPU capabilities.

## 3. Code Architecture & Affected Callers

- `src/hawedit/render.py`:
  - `quality_args`: keep function signature compatible for backwards-compatibility; add `deliverable_video_args(encoder: Encoder, crf: int = 20, fps: float = 25.0) -> list[str]`.
  - `crop_filter`: support Lanczos scaling and light unsharp post-scaling.
  - `render_clip`:
    - Remove `-threads 1` from decode input flags.
    - Append BT.709 color tags: `["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]`.
    - Apply deliverable encoder flags.
- `tests/test_render.py`:
  - Existing `test_quality_args_nvenc_sets_vbr_cq_not_crf` tests base quality args.
  - Add tests for deliverable encode profile args, filter generation with Lanczos + unsharp, and color metadata flags.
