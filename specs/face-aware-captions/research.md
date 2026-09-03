# Research: Face-Aware Caption Placement (Task T2.7)

## 1. Grounding & Spec
Per `specs/pro-grade-program/tasks.md` Task T2.7:
> **T2.7** | **P2** | **Face-aware caption placement.** If the tracked face box intersects the caption band in any frame, move the band (top/bottom) for that shot; never overlap. `captions.py:229-231` fixed band. Proof required: A: geometry test. B: zero overlapping frames measured on ep29 renders (media tier). C: T1.2 clause.

In `src/hawedit/captions.py`:
- Captions currently default to `alignment = 2` (bottom-centered) with `margin_v = 360` (`VIRAL_THEME`).
- In 1080x1920 PlayRes, the bottom caption band occupies vertical range `Y = 1300 .. 1650`.
- If a speaker sits low in the frame, leans forward, or if framing positions the face lower, the bottom caption text directly covers the subject's chin, mouth, or neck.

## 2. Geometry & Placement Analysis
- Bottom Caption Band: `[1300, 1650]` px on 1080x1920 canvas (`alignment = 2`, `margin_v = 360`).
- Top Caption Band: `[200, 520]` px on 1080x1920 canvas (`alignment = 8`, `margin_v = 240`).
- Face Box in Canvas Coordinates:
  A face with `center_y` and `face_height` occupies vertical span `[center_y - face_height / 2, center_y + face_height / 2]`.
- Overlap Condition:
  An overlap occurs when:
  `face_bottom >= band_top` and `face_top <= band_bottom`.
- Resolution:
  When any sampled frame during a caption event's time span intersects the bottom caption band, the caption event dynamically switches to `KurdishTop` (`alignment = 8`, `margin_v = 240`), moving the subtitle text to the top of the canvas and completely clearing the face region.

## 3. Native ASS Implementation
In `build_ass`:
- Declare both `Kurdish` (bottom: `alignment=2, margin_v=theme.margin_v`) and `KurdishTop` (top: `alignment=8, margin_v=240`) styles in `[V4+ Styles]`.
- Provide `face_intervals: Sequence[tuple[int, int, int, int]] | None = None` (where each item is `(start_ms, end_ms, face_top_y, face_bottom_y)`) or `face_y_boxes`.
- For each dialogue event:
  - If any face interval overlapping the event's time range has `face_bottom_y >= 1300 and face_top_y <= 1650`:
    Use style `KurdishTop`.
  - Otherwise, use default style `Kurdish`.
