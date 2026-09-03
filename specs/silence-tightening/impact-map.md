# Impact Map: Silence Tightening Wired End-to-End (Task T3.3, ADR D-266)

## Affected Modules & Callers
1. `src/hawedit/silence.py`:
   - Extend with `SilencePlan`, `plan_silence_tightening`, `remap_timestamp`, `silence_trim_filter`.
   - Reused callers: existing `tighten_silence`, `tighten_sentences`, `tighten_clip` maintain backwards compatibility.
2. `src/hawedit/render.py`:
   - `render_clip`: accepts `silence_plan: SilencePlan | None = None`.
   - Applies filtergraph splicing when `silence_plan.total_removed_ms > 0`.
   - Updates `assert_encoded_span` check with `effective_duration_ms = duration_ms - silence_plan.total_removed_ms`.
   - Callers: `pipeline.py`, `test_render.py`, `test_pipeline.py`.
3. `src/hawedit/pipeline.py`:
   - `build_parser`: add `--silence-threshold-ms` (default 0) and `--silence-target-gap-ms` (default 150).
   - `run_pipeline`: parameterize `silence_threshold_ms` and `silence_target_gap_ms`. If enabled, compute `SilencePlan`, update `Clip.output.silence_removed_ms`, update `selected` sentences for `build_ass`, remap `planned_punch_ins` and `focus_points`, and pass `silence_plan` to `render_clip`.
4. `src/hawedit/delivery.py`:
   - Verified that Clause 4 (`silence_math_mismatch`) strictly expects `clip.output.silence_removed_ms == span_ms - measured_audio_dur`.
   - Clause 1 strictly matches `clip.output.durations`.

## Caller Analysis
- `pipeline.py` is the primary caller of `render_clip`.
- Direct test callers of `render_clip` in `tests/test_render.py` pass `silence_plan=None` by default and remain 100% green.
- Existing tests for `silence.py` in `tests/test_silence.py` verify mathematical shifting. New tests will cover plan generation and filter creation.
