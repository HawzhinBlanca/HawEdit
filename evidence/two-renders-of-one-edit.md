# Level B Evidence: Reproducibility Proof of Deliverable Encode (Task T1.7)

```yaml
commit: 8b7a7a43865efdad91f8dc648e8bdeb4500eaae4
media_sha256: 207b034ee2eb90a3152e65630f34bd24d8bba77ce54855b574d75517a2c3fcb2
host: HAWAPC01
command: python scratch/render_repro_ep29.py
date: 2026-09-04T17:35:00Z
blueprint_ref: §7.8, §4.3
```

## 1. Summary of Measurement

Per `specs/pro-grade-program/tasks.md` Task T1.7 and `BLUEPRINT.md` §7.8, two independent renders of the canonical social clip (`ep29-VbX8UWwl1c4-s25-25`) were executed from identical inputs on host `HAWAPC01` using the pinned deliverable profile:
- **Hardware Encoder**: NVIDIA NVENC on NVIDIA GeForce RTX 3090 Ti.
- **Pinned Encoder Flags**: `-preset p6 -profile:v high -bf 3 -spatial-aq 1 -temporal-aq 1 -rc vbr -cq 20 -b:v 0 -g 50`.
- **Colour Primaries**: `-color_primaries bt709 -color_trc bt709 -colorspace bt709`.
- **Scaling & Sharpening**: `scale=1080:1920:flags=lanczos,unsharp=5:5:0.5:5:5:0.0`.
- **Audio Chain**: 2-pass linear EBU R128 loudnorm (`I=-14.0 LUFS, TP=-1.0 dBTP, LRA=11.0 LU`) + native speech filter chain (`afftdn`, `deesser`, presence EQ).

## 2. Quantitative Verification Results

| Artifact / Metric | Run 1 (Canonical Deliverable) | Run 2 (Reproducibility Run) | Verification Verdict |
|---|---|---|---|
| **Video File Size** | 115,258,076 bytes | 115,258,076 bytes | **IDENTICAL** |
| **Video SHA-256** | `207b034ee2eb90a3152e65630f34bd24d8bba77ce54855b574d75517a2c3fcb2` | `207b034ee2eb90a3152e65630f34bd24d8bba77ce54855b574d75517a2c3fcb2` | **BIT-EXACT MATCH** |
| **Subtitles (ASS)** | 7,002 bytes | 7,002 bytes | **BYTE-IDENTICAL** |
| **Contract (JSON)** | Canonical schema v1 | Canonical schema v1 | **IDENTICAL** (minus timestamps) |
| **PSNR (FFmpeg)** | — | — | **`inf dB`** (Threshold: $\ge 45.0$ dB) |
| **Render Runtime** | ~23.5s | 21.03s | Real-time factor: $0.39\times$ |

## 3. NVENC Determinism Assessment

While hardware NVENC encoders are generally subject to GPU thread execution variations and not guaranteed to be bit-exact across different driver builds, with fully pinned encoding arguments (`-preset p6 -profile:v high -bf 3 -spatial-aq 1 -temporal-aq 1 -rc vbr -cq 20 -b:v 0 -g 50`) on identical hardware, the two runs achieved **exact bit-identical output** and **infinite PSNR**.

This satisfies Level B proof requirements for Task T1.7 and validates the automated regression test `test_two_renders_of_one_edit_agree` in `tests/test_render.py`.
