# EARS

| ID | Requirement | Named Regression |
| --- | --- | --- |
| IM1 | WHEN a copied executable is replaceable, THE test preparation SHALL mutate actual bytes and permit every existing cache invalidation assertion. | test_executable_mutation_changes_real_bytes; test_actual_ffmpeg_byte_drift_invalidates_ingest_cache |
| IM2 | WHEN an actual Windows lease is released within the finite budget, THE test preparation SHALL replace the real copied bytes without changing installed tools. | test_executable_mutation_waits_for_released_windows_lease |
| IM3 | WHEN a Windows read lease remains held beyond the budget, THE test preparation SHALL fail visibly, retain both original byte sets and never wait without bound. | test_executable_mutation_refuses_retained_windows_lease |
| IM4 | WHEN input is missing or the budget is nonfinite/nonpositive, THE test preparation SHALL refuse without changing destination bytes. | test_executable_mutation_missing_input_is_not_retried; test_executable_mutation_rejects_invalid_budget |

Windows lease claims require actual Windows execution. Non-Windows control branches prove ordinary filesystem behavior/refusal only, never simulate Windows support.
