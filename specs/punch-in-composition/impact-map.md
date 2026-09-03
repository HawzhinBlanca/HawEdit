# Impact Map — Composition Line Under Punch-Ins (`specs/punch-in-composition`)

## 1. Modified Files
- `src/hawedit/render.py`: `crop_filter` expression calculation for `y_expr`.
- `tests/test_render.py`: Unit tests for `crop_filter` punch-in expressions.
- `security/wsl-asr-vex.json`: Updated `source_sha256` after `render.py` edit.

## 2. Downstream Callers
- `render.render_clip`: Passes `face_center_y` to `crop_filter` during render generation.
- No public function signatures modified.
- Purely internal ffmpeg expression improvement.
