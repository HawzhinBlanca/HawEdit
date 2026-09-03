# Research: Wide-Shot Handling & Blurred-Fill Layout (Task T2.2)

## 1. Grounding & Context
Per `specs/pro-grade-program/tasks.md` Task T2.2:
> **T2.2** | **P1** | **Wide-shot handling.** When the measured face-height share in a shot < `TARGET_FACE_HEIGHT_SHARE`, either zoom past `MAX_VERTICAL_ZOOM` up to a **sharpness floor** (Laplacian variance of the face region ≥ the median of the close-up shots × 0.6, measured), or switch that shot to a **blurred-fill layout** (scaled wide frame over a blurred, darkened copy — one ffmpeg `split/boxblur/overlay`). Decide per shot by measurement, record which in the contract.
> Proof required: A: geometry + layout tests. B: re-render s25-25; face share ≥ 0.12 in ≥ 95 % of frames; sharpness numbers; VMAF vs mezzanine; frames inspected. C: T1.2. E. Decider: Hawa picks zoom vs layout after seeing both renders (taste).

In `research.md` §3.1:
A multi-angle podcast or interview frequently cuts to a wide master shot where both speakers sit at the table.
In such shots, the face height share is typically 6–8%, far below `TARGET_FACE_HEIGHT_SHARE` (0.18 / 18%).
If cropped vertically with `MAX_VERTICAL_ZOOM = 1.6`, the face occupies only ~10-12% of the vertical frame, leaving distant subjects in a narrow slit.
If cropped with aggressive vertical zoom (e.g. 2.5x–3.0x), the small face becomes soft and blurry unless the source resolution and focus provide sufficient sharpness.
When the face sharpness falls below the sharpness floor ($0.6 \times \text{median closeup variance}$), the shot must switch to the industry-standard **blurred-fill layout** (sharp 16:9 frame centered over an aspect-fitted, blurred, darkened 9:16 background).

## 2. Blurred-Fill Filter Architecture
In FFmpeg:
```
split=2[fg][bg];
[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2,eq=brightness=-0.15[bg_blur];
[fg]scale=1080:-2:flags=lanczos,unsharp=5:5:0.5:5:5:0.0[fg_sharp];
[bg_blur][fg_sharp]overlay=(W-w)/2:(H-h)/2
```
- Foreground: 16:9 scaled to 1080 width ($1080 \times 608$), positioned at $Y = (1920 - 608) / 2 = 656$.
- Background: Full vertical canvas ($1080 \times 1920$) filled with a blurred, darkened copy of the frame.
- Bottom caption band ($Y = 1300..1650$) sits over the blurred, darkened background area, ensuring perfect subtitle legibility without covering the action in the wide shot.

## 3. Sharpness Floor & Layout Decision
- `decide_wide_shot_layout(face_height_share, face_sharpness, closeup_sharpness_median=None, target_share=0.18, max_zoom=2.5, default_sharpness_floor=50.0)`:
  - If `face_height_share >= target_share`: return `("crop", 1.0)`.
  - If `face_height_share < target_share`:
    - `floor = closeup_sharpness_median * 0.6` if `closeup_sharpness_median` else `default_sharpness_floor`.
    - If `face_sharpness >= floor`:
      - Return `("zoom", min(target_share / face_height_share, max_zoom))`.
    - Else:
      - Return `("blurred_fill", 1.0)`.
