# ASR worker diagnostic EARS criteria

| ID | Criterion | Named regression |
|---|---|---|
| WD-1 | WHEN a WSL worker fails, THE canonical ASR producer SHALL report failure without prescribing runtime setup as its cause. | test_wsl_content_failure_does_not_recommend_reprovisioning |
| WD-2 | WHEN a worker's long traceback ends in a concrete alignment failure, THE pipeline report SHALL retain its bounded diagnostic tail, including the interval and frame/token cause, without changing the shared report cap. | test_wsl_worker_error_tail_survives_pipeline_reason_budget |
| WD-3 | WHEN a worker returns without its required output, THE producer SHALL refuse and report its exit code and missing output instead of returning a transcript. | test_wsl_missing_worker_output_remains_a_refusal |
| WD-4 | WHEN a canonical receipt is absent, THE runtime SHALL retain the actionable setup prerequisite. | test_missing_wsl_receipt_still_reports_setup_prerequisite |

No criterion changes decoding, alignment, canonical text, checkpoints, data
sharing, signing, publication or acceptance. Test fault/transport inputs are
synthetic. Actual ZAR38 evidence remains a separate real-model result.
