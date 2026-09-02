# Plan — Audit Remediation & Polish

## Summary of Defects / Improvements

1. **Subprocess timeout in `render_clip`**: Add `timeout` to ffmpeg encode in `render.py`, converting `subprocess.TimeoutExpired` into `RenderError`.
2. **Duplicate interpolation**: Refactor `crop_filter` non-punch branch in `render.py` to use `_interpolated()`.
3. **Encapsulation / Private Imports**: Export public symbols `strict_bool`, `json_object_fields`, `sv6d_from_json`, `interactive_confirm`, `proxy_dimensions`, `build_and_run`, `BUILD_ERRORS`, `publish_runtime_candidate` (retaining private aliases for backward compatibility) and update importing modules.
4. **Redundant Dimension Probing**: Update `_steady_camera` in `pipeline.py` to take optional `source_dimensions`.
5. **Top-level Import in `gemini.py`**: Move `replace` import to module top-level.

## Files & Changes

| File | Change |
|---|---|
| `src/hawedit/render.py` | Add timeout & `TimeoutExpired` handling to `render_clip`; route non-punch interpolation through `_interpolated()`. |
| `src/hawedit/transcripts.py` | Export `json_object_fields` (alias `_json_object_fields`). |
| `src/hawedit/boundary.py` | Export `strict_bool` and `json_object_fields` (aliases `_strict_bool`, `_json_object_fields`). |
| `src/hawedit/clip.py` | Export `sv6d_from_json` (alias `_sv6d_from_json`). |
| `src/hawedit/proposals.py` | Export `interactive_confirm` (alias `_interactive_confirm`). Update import of `proxy_dimensions`. |
| `src/hawedit/promotion.py` | Import `interactive_confirm` from `hawedit.proposals`. |
| `src/hawedit/workflow_control.py` | Import `interactive_confirm` from `hawedit.proposals`. |
| `src/hawedit/judge.py` | Import `json_object_fields`, `strict_bool` from `hawedit.boundary` and `sv6d_from_json` from `hawedit.clip`. |
| `src/hawedit/pipeline.py` | Export `proxy_dimensions`, `build_and_run`, `BUILD_ERRORS` (aliases `_proxy_dimensions`, `_build_and_run`, `_BUILD_ERRORS`). Allow `_steady_camera` to accept `source_dimensions`. |
| `src/hawedit/durable.py` | Import `BUILD_ERRORS`, `build_parser` from `hawedit.pipeline`. |
| `src/hawedit/durable_workflow.py` | Import `build_and_run`, `build_parser` from `hawedit.pipeline`. |
| `src/hawedit/wsl_setup.py` | Export `publish_runtime_candidate` (alias `_publish_runtime_candidate`), update template script. |
| `src/hawedit/gemini.py` | Move `replace` import to top-level. |
| `tests/test_render.py` | Add unit test verifying `render_clip` timeout behavior. |

## Risks & Mitigations

- **Risk**: Renaming symbols might break external callers or tests.
  **Mitigation**: Maintain `_` private alias aliases in every module so any caller expecting the legacy name continues to work without interruption.
- **Risk**: Render timeout too short for long clips.
  **Mitigation**: Scale timeout dynamically: `max(60.0, (duration_ms / 1000.0) * 10.0)` gives at least 1 minute for short clips and 10x real-time for longer clips.

Approved-by: Hawa
