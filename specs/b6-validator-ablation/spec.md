# Spec: Validator Off Default & WER Ablation (`specs/b6-validator-ablation`)

EARS acceptance criteria (`WHEN <trigger>, THE <system> SHALL <response>`). Every criterion names the automated test(s) that verify it in `tasks.md`.

## AC1 — Default off & explicit CLI opt-in (`--validate-asr` / `--no-validate-asr`)
- WHEN `hawedit.pipeline` runs with `--omni-asr` and no explicit validator flag (or with `--no-validate-asr`), THE producer (`create_omni_asr_producer`) SHALL construct Stage 1 with `validate_hard_segments=False`; WHEN `--validate-asr` is passed (and NOT beside `--transcript` alone), THE producer SHALL run with `validate_hard_segments=True` and enforce all existing Qwen validator contracts; WHEN `--validate-asr` or `--no-validate-asr` is passed without `--omni-asr`, THE CLI SHALL refuse before Stage 0.
  - Tests: `tests/test_validator_ablation.py::test_cli_defaults_validator_off_and_opts_in_with_validate_asr`, `tests/test_pipeline.py::test_cli_refuses_validate_asr_flags_without_omni_asr`.

## AC2 — Validator-off path requires neither `rzgar` weights nor `qwen-asr`
- WHEN `OmniAsrProducer` or `WslOmniAsrProducer` runs with `validate_hard_segments=False`, THE host SHALL NOT call `ModelStore().assert_available(VALIDATOR_MODEL_ID)` or `verified_checkpoint_access(VALIDATOR_MODEL_ID, ...)` and SHALL omit `"validator_model_dir"` (or include `"validate_hard_segments": false`) cleanly across the WSL request boundary, and `asr_resume.worker_journal` SHALL NOT require `importlib.metadata.version("qwen-asr")` or `ModelStore().verify_checkpoint(VALIDATOR_MODEL_ID, ...)`.
  - Tests: `tests/test_validator_ablation.py::test_native_and_wsl_producers_skip_validator_weights_when_disabled`, `tests/test_validator_ablation.py::test_worker_and_journal_run_without_qwen_asr_or_validator_dir_when_disabled`.

## AC3 — Validator-on path stays 100% strict (`D-278`, `D-324`)
- WHEN `validate_hard_segments=True`, THE worker request, `worker_journal` package/checkpoint binding, `QwenSoraniValidator` loading, `_validate_hard_segments` execution, and serialized `RawTranscript` JSON SHALL preserve strict refusal on missing `validator_model_dir`/`rzgar` weights/failed completion and match existing `RawTranscript` schema and bytes.
  - Tests: `tests/test_validator_ablation.py::test_validator_on_preserves_strict_request_journal_and_origin_contracts`.

## AC4 — Honest `SegmentOrigin` and `PipelineRun` provenance without falsifying escalation
- WHEN a `RawTranscript` is assembled with validation disabled, EVERY `SegmentOrigin` SHALL carry `outcome="validator-disabled"`, `escalated=False`, `validator=None`, `validator_text=None`, `rejection_reason=None`, and `route_reason` preserving the counterfactual `select_for_validation` reason; `RawTranscript._validate_origins()` SHALL accept a uniformly `"validator-disabled"` batch, SHALL refuse any mixed batch combining `"validator-disabled"` with active validation outcomes, and `PipelineRun.to_dict()` SHALL report `routing_status="validator-disabled"` with `escalated=0`.
  - Tests: `tests/test_validator_ablation.py::test_segment_origins_record_validator_disabled_uniformly_and_refuse_mixed_batches`, `tests/test_validator_ablation.py::test_pipeline_report_never_claims_escalations_when_validator_disabled`.

## AC5 — Cache & journal isolation between validator-on and validator-off runs (`D-136`)
- WHEN `TranscriptStore.reusable_raw` or `worker_journal` evaluates reuse on identical audio and model weights, validator-enabled (`validate_hard_segments=True`) and validator-disabled (`validate_hard_segments=False`) runs SHALL have distinct `admission_policy` / `validator_mode` bindings so neither reuses the other's cached transcript or worker operations.
  - Tests: `tests/test_validator_ablation.py::test_transcript_store_and_worker_journal_separate_validator_on_and_off_caches`.

## AC6 — Paired WER & wall-time ablation benchmark protocol
- WHEN the ablation runner executes paired `validate_hard_segments=False` vs `validate_hard_segments=True` passes on the same set of `>= 20` real Sorani clips with human reference text (`#1` / `B5`), THE ablation report SHALL record per-clip and aggregate WER, normalized CER, RTF, validator invocation count, and CTC realignment failures under exact hardware/checkpoint provenance to inform the final retire-or-keep ADR amendment.
  - Tests: `tests/test_validator_ablation.py::test_paired_ablation_scorer_computes_exact_wer_cer_and_speedup_deltas`.
