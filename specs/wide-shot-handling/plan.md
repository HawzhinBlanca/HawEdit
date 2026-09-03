# Plan: Wide-Shot Handling & Blurred-Fill Layout (Task T2.2)

Approved-by: Hawa

## Overview
Provide professional handling for wide shots (where measured face-height share is below target) by supporting both sharpness-governed deep zoom and the industry-standard blurred-fill layout (scaled sharp 16:9 wide frame over a blurred, darkened 9:16 background).

## Architecture
1. In `src/hawedit/render.py`:
   - Add `BLURRED_FILL = "blurred_fill"` to `Reframe` enum.
   - Implement `blurred_fill_filter(source_width, source_height, target_width=1080, target_height=1920, *, blur_radius=20, brightness=-0.15, lanczos=False, unsharp=False) -> str`.
   - Implement `decide_wide_shot_layout(...)`.
   - Update `render_clip` to support `reframe=Reframe.BLURRED_FILL`.
2. In `src/hawedit/pipeline.py`:
   - Map `Reframe.BLURRED_FILL: "blurred_fill"`.
3. In `tests/test_render.py`:
   - Test geometry and string generation of `blurred_fill_filter`.
   - Test `decide_wide_shot_layout` thresholds and sharpness checks.
   - Test video rendering under `Reframe.BLURRED_FILL`.
