# Impact Map: Wide-Shot Handling & Blurred-Fill Layout (Task T2.2)

## Modified Files
- `src/hawedit/render.py`:
  - Class `Reframe`: added enum member `BLURRED_FILL = "blurred_fill"`.
  - Function `blurred_fill_filter(...)`: constructs the FFmpeg filter chain for blurred-fill wide-shot presentation.
  - Function `decide_wide_shot_layout(...)`: decides between standard crop, deep zoom, or blurred-fill layout based on face height share and measured sharpness.
  - Function `render_clip`: handles `Reframe.BLURRED_FILL`, bypassing focus points and using `blurred_fill_filter`.
- `src/hawedit/pipeline.py`:
  - Updated reframe name mapping to include `Reframe.BLURRED_FILL: "blurred_fill"`.
- `tests/test_render.py`:
  - Tests for filter string generation, layout decision thresholds, and synthetic rendering with blurred-fill layout.
