# Tasks: Eased Push-Ins (Task T2.6)

| Status | ID | Task | Acceptance Criteria | Cited Tests |
|---|---|---|---|---|
| TODO | **T1** | Implement `DEFAULT_PUSH_ZOOM`, `DEFAULT_PUSH_STEP_MS`, `shot_spans`, and `eased_push_schedule` in `src/hawedit/render.py` | Criterion 1, Criterion 2, Criterion 3 | `test_shot_spans_partitions_clip_into_contiguous_intervals`, `test_eased_push_schedule_generates_smoothstep_progression` |
| TODO | **T2** | Integrate eased push-in schedule into pipeline/render and verify end-to-end rendering via FFmpeg | Criterion 4 | `test_render_clip_supports_eased_push_in_schedule` |
