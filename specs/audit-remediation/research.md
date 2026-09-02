# Research — Audit Remediation & System Polish

## 1. Context & Motivation

A comprehensive audit of HawEdit identified 5 specific areas for correctness hardening, code deduplication, encapsulation cleanup, and efficiency improvements:

1. **Subprocess timeout in `render_clip`**: `subprocess.run` at `render.py:806` lacks a timeout, risking unbounded hangs on GPU/NVENC deadlocks.
2. **Duplicate interpolation in `crop_filter`**: `render.py:525-551` duplicates `_interpolated()`'s piecewise-linear ffmpeg expression builder.
3. **Cross-module private imports**: Multiple modules (`judge.py`, `proposals.py`, `promotion.py`, `workflow_control.py`, `durable.py`, `durable_workflow.py`, `wsl_setup.py`) import `_private` symbols across module boundaries.
4. **Redundant `ffprobe` calls in `_steady_camera`**: `_steady_camera` in `pipeline.py:1431` re-probes video dimensions via `ffprobe` rather than reusing known dimensions.
5. **Deferred import in `gemini.py`**: `from dataclasses import replace` inside `GeminiJudge.judge_with_count` (L518) instead of module top-level.

## 2. Symbol Mapping & Invariants

### 2.1 `render.py` Subprocess Execution
- Target: `render_clip()`
- Invariant: Kurdish invariant #2 + §8.3 artifact validation.
- Subprocess call: Encodes staging MP4 with ffmpeg.
- Behavior on timeout: Must raise `RenderError` with clear diagnostic context, clean up temporary staging file in `finally`, and never publish a truncated or corrupt artifact.
- Timeout calculation: Proportional to clip duration `max(60.0, (duration_ms / 1000.0) * 10.0)`.

### 2.2 `render.py` Piecewise Interpolation
- Target: `_interpolated(points, fallback)` and `crop_filter()`
- `_interpolated` builds:
  `if(lt(t\,end_s)\,(here+(there-here)*(t-start_s)/span)\,expression)`
- `crop_filter` non-punch branch computes `positions` (clamped against `crop_w`) and `times`, and applies the exact same logic.
- Unification: Pass `list(zip(times, positions))` to `_interpolated` with fallback `(source_width - crop_w) // 2`.

### 2.3 Cross-Module Boundaries & Encapsulation
- Symbols to promote to public (with backward-compatible private aliases):
  - `boundary.py`: `strict_bool`, `json_object_fields`
  - `transcripts.py`: `json_object_fields`
  - `clip.py`: `sv6d_from_json`
  - `proposals.py`: `interactive_confirm`
  - `pipeline.py`: `proxy_dimensions`, `build_and_run`, `BUILD_ERRORS`
  - `wsl_setup.py`: `publish_runtime_candidate`
- All affected importing modules will be updated to import public names.

### 2.4 Dimension Probing
- `pipeline.py`: `_steady_camera(points, source, ffmpeg, source_dimensions=None)`
- If `source_dimensions` is supplied, use it; otherwise probe via `proxy_dimensions(source, ffmpeg)`.
- `run_pipeline` passes known dimensions from the single probe ahead of `render_clip`.

### 2.5 `gemini.py` Imports
- Move `replace` to top-level `from dataclasses import dataclass, replace`.
