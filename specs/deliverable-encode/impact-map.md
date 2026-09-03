# Impact Map — Deliverable Encode Profile (`specs/deliverable-encode`)

## Symbols Modified

| File | Symbol | Nature of Change | Callers Affected |
| :--- | :--- | :--- | :--- |
| `src/hawedit/render.py` | `deliverable_video_args` | New function | `render_clip`, `tests/test_render.py` |
| `src/hawedit/render.py` | `crop_filter` | Add Lanczos + unsharp options | `render_clip`, `tests/test_render.py` |
| `src/hawedit/render.py` | `render_clip` | Update ffmpeg command generation (remove `-threads 1`, add color tags & deliverable args) | `pipeline.py`, `tests/test_render.py`, `tests/test_pipeline.py` |
| `tests/test_render.py` | New unit tests | Automated tests for T2.10 args and filters | Test runner |

## Callers and Invariants Checked

- `quality_args`: Retained untouched for backwards compatibility with any existing caller.
- `render_clip`:
  - `crop_filter` output remains compatible with `subtitle_filter` chaining.
  - `-pix_fmt yuv420p` remains after video encoder args.
  - `-movflags +faststart` remains for streaming moov atom placement.
  - `-threads 1` removed from ffmpeg input arguments (enabling parallel multi-threaded input decode).
