# Specification — Audit Remediation & Polish

## Acceptance Criteria

- **AC-1 (Render Subprocess Timeout):** WHEN `render_clip` executes the `ffmpeg` encode subprocess, THE system SHALL enforce a deterministic timeout based on the clip duration (`max(60.0, (duration_ms / 1000.0) * 10.0)`), AND on timeout, THE system SHALL raise a `RenderError` stating that the encode timed out.
- **AC-2 (Interpolation Deduplication):** WHEN `crop_filter` constructs piecewise-linear ffmpeg expressions for dynamic reframe (both non-punch and punch paths), THE system SHALL share the unified `_interpolated` implementation without duplicating the interpolation loop.
- **AC-3 (Clean Encapsulation & Public Exports):** WHEN cross-module functionality is imported (such as JSON validation helpers, proxy dimension probes, interactive confirmation, build dispatch, and WSL runtime publication), THE importing modules SHALL import documented public symbols instead of `_private` names.
- **AC-4 (Efficient Steady Camera Dimensions):** WHEN `_steady_camera` is called within `run_pipeline`, THE system SHALL accept and reuse pre-probed source dimensions rather than launching redundant `ffprobe` child processes.
- **AC-5 (Clean Module Imports in Gemini):** WHEN `GeminiJudge` is executed, `dataclasses.replace` SHALL be imported at module top-level in `gemini.py`.
