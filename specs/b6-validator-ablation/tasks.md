# Tasks: Validator Off Default & WER Ablation (`specs/b6-validator-ablation`)

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"

All tasks follow `AGENTS.md` (test-first, smallest correct change, single-writer worktree `HawEdit-lane-2`, gate pass via `scripts/verify.sh` on lead before flipping ledger rows).

- [x] T1 Add uniform `"validator-disabled"` `SegmentOrigin` contract in `src/hawedit/transcripts.py` and honest `routing_status` handling in `PipelineRun.to_dict()` (`src/hawedit/pipeline.py`); AC4 tests in `tests/test_validator_ablation.py`: `test_validator_disabled_origin_rejects_mixing_and_flags_escalated`, `test_pipeline_report_never_claims_escalations_when_validator_disabled`.
- [x] T2 Thread `validate_hard_segments: bool` through `create_omni_asr_producer`, `OmniAsrProducer`, `WslOmniAsrProducer` (`src/hawedit/asr.py`), `asr_worker.py`, `asr_resume.worker_journal`, and `--validate-asr` / `--no-validate-asr` CLI flags (`src/hawedit/pipeline.py`), making validator OFF the default while keeping validator ON strict and cache-isolated (`admission_policy` `+validator-off`); AC1–AC3 & AC5 tests in `tests/test_validator_ablation.py` and `tests/test_pipeline.py`: `test_cli_defaults_validator_off_and_opts_in_with_validate_asr`, `test_native_and_wsl_producers_skip_validator_weights_when_disabled`, `test_worker_and_journal_run_without_qwen_asr_or_validator_dir_when_disabled`, `test_validator_on_preserves_strict_request_journal_and_origin_contracts`, `test_transcript_store_separates_validator_on_and_off_caches`, `test_factory_native_and_wsl_share_context_and_completion_policy`.
- [x] T3 Record ADR `D-341` in `DECISIONS.md` (validator off default pending paired WER measurement), add paired ablation comparison helper (`test_paired_ablation_scorer_computes_exact_wer_cer_and_speedup_deltas`, `test_every_decision_the_docs_cite_exists`), and coordinate VEX re-pin at integration.
- [ ] T4 Run live paired WER & RTF ablation (`--no-validate-asr` vs `--validate-asr` on `>= 20` real clips with human reference text `#1` / `B5` and staged `rzgar` + `qwen-asr`), write `evidence/b6-validator-ablation-YYYY-MM-DD.md`, and amend `D-341` with the measured keep-or-retire verdict.

## Definition of Done
- AC1–AC6 automated tests pass in full `verify.sh` and CI.
- Paired WER/CER/RTF ablation on `>= 20` real Kurdish clips recorded in `evidence/` and cited in `D-341`.
