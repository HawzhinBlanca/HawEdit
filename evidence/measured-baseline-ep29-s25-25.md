# Measured Baseline — ep29-VbX8UWwl1c4-s25-25

```yaml
commit: dce5e76a49e57e1926b3fed03ac293ad8ac69779
media_sha256: b42da4783cd03f6a27cbe430f72a2a5693330e26712a34cf60f58d56bd8316d4
host: HAWAPC01
command: python -m hawedit.measure work/ep29-VbX8UWwl1c4-s25-25/ep29-VbX8UWwl1c4-s25-25.mp4 --ass work/ep29-VbX8UWwl1c4-s25-25/ep29-VbX8UWwl1c4-s25-25.ass --out work/ep29-VbX8UWwl1c4-s25-25/ep29-VbX8UWwl1c4-s25-25.measured.json
date: 2026-09-02T17:24:41Z
```

## 1. Ground Truth Measurement Record

Independent ground-truth measurement performed by `hawedit.measure` (AST-isolated from `render.py` and `pipeline.py`).

### File & Container Properties
- **Path**: `work/ep29-VbX8UWwl1c4-s25-25/ep29-VbX8UWwl1c4-s25-25.mp4`
- **File Size**: 21,106,780 bytes
- **SHA-256**: `b42da4783cd03f6a27cbe430f72a2a5693330e26712a34cf60f58d56bd8316d4`
- **Resolution**: 1080×1920 (vertical 9:16)
- **Frame Rate**: 25.0 fps (`25/1`)
- **Duration**: 56,600 ms (1,415 frames)
- **Bitrate**: 2,983.29 kbps
- **Video Codec**: `h264`, `yuv420p`, color space `bt709`

### Audio Dynamics (EBU R128 & Silencedetect)
- **Audio Codec**: `aac`, 48,000 Hz, 2 channels (stereo)
- **Integrated Loudness**: −14.20 LUFS
- **True Peak**: −0.90 dBFS
- **Loudness Range (LRA)**: 2.20 LU
- **Detected Silences (≥ 250 ms, −30 dB)**: 18 intervals
  - Total silence: 6,743 ms (11.91% of clip)
  - Longest gap: 545 ms (at 44,117–44,662 ms)
  - Shortest detected pause: 263 ms

### Visual Shot Cuts (`scdet > 0.3`)
- **Detected Cut Count**: 10
- **Cut Timestamps (ms)**: `[560, 11040, 17080, 20840, 26000, 34240, 39680, 44640, 47680, 55640]`

### Face Detection & Tracking Framing (OpenCV Haar at 5 fps / 200 ms interval)
- **Total Samples**: 283 frames
- **Frames with Detected Face**: 159 frames (56.18% share)
  - Note: During 17–25 s (wide table shot) and 0–1 s (host drinking), face share is below detection floor or off-center.
- **Median Face Height Share**: 0.2370 (23.7% of vertical frame height in detected frames)
- **Median Y-Center Share**: 0.3951 (matches target composition line ~0.38)

### Subtitle Ink & Energy Analysis (against `.ass` dialogue cues)
- **Dialogue Cues Evaluated**: 47 events
- **Ink Energy Detected Share**: 1.0000 (100% of dialogue cues exhibit high Laplacian variance in caption band `0.65·H` to `0.90·H`)
- **Median Contrast Ratio**: 3.26:1
