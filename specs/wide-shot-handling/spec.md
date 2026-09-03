# Spec: Wide-Shot Handling & Blurred-Fill Layout (Task T2.2)

## Acceptance Criteria (EARS Format)

- **AC-1 (Blurred-Fill Filter Graph Construction)**:
  WHEN requested to generate a blurred-fill layout filter via `blurred_fill_filter(...)`,
  THE system SHALL emit an FFmpeg filter chain that splits the input, creates a blurred and darkened background filling the target canvas, and overlays the scaled sharp foreground centered at `(W-w)/2:(H-h)/2`.

- **AC-2 (Wide-Shot Layout Decision Logic)**:
  WHEN evaluating a shot whose measured face-height share < `TARGET_FACE_HEIGHT_SHARE`,
  THE system SHALL select `"zoom"` (up to `max_zoom`) when face sharpness $\ge$ the sharpness floor, and select `"blurred_fill"` when face sharpness < the floor.

- **AC-3 (Reframe Enum & Honest Execution)**:
  WHEN `Reframe.BLURRED_FILL` is supplied to `render_clip`,
  THE system SHALL execute the render using `blurred_fill_filter`, without requiring `focus_points`, and record `reframe=Reframe.BLURRED_FILL` in `RenderResult`.

- **AC-4 (Pixel Execution & Canvas Coverage)**:
  WHEN rendering a video using `blurred_fill_filter`,
  THE output video SHALL produce exact 1080x1920 vertical frames with darkened blurred pillarbox/letterbox bands and sharp center content.
