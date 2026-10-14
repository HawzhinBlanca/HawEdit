# Impact map: fused-checkpoint drafting (v12)

Positions are line numbers on `6fe060d` (`codex/evidence-based-studio`). Every changed symbol is listed with its callers and the tests that must cover it.

## asr.py
| Symbol | Change | Callers | Tests |
|---|---|---|---|
| `resolve_champion_adapter` (222-269) | unchanged; a sibling `resolve_champion_checkpoint` is added | `pipeline.py:5439-5453`; `studio_host.py:143-144, 203-204, 228` | `test_asr.py` champion tests; `test_studio_host.py` |
| `OmniAsrBackend.__init__` (517-545) | new `fused_checkpoint`; LLM default `cuda:1` | `asr.py` adapter and producer; `asr_worker.py:100`; tests | `test_asr.py` device tests; `test_champion_held_assets.py:225` |
| `OmniAsrBackend.adapter_name` (552-570) | returns `fused:<sha>` for fused | `asr.py:896, 913, 921, 925`; `asr_resume.py:232-233` | `test_adapter_identity.py` |
| `OmniAsrBackend._load` / `_load_adapted_llm` (572-646, 719-811) | fused branch without PEFT; assets subset | `_load` call sites | `test_asr.py:94-137` loader tests (fakes) |
| `WslOmniAsrProducer.model_identity` / request (1435-1444, 1545-1631) | `fused_checkpoint` field and identity re-check | `create_omni_asr_producer` (1635-1650) | `test_asr.py` worker/producer tests; `test_trusted_producer_parity.py` |
| `create_omni_asr_producer` (1635-1650) | accepts a checkpoint | `pipeline.py` around 5450 | `test_pipeline.py` |

## Other files
| Symbol | Change | Callers | Tests |
|---|---|---|---|
| `asr_worker.run_request` (53-168; regex at 110) | accepts `fused:[a-f0-9]{64}`; free-VRAM check | WSL subprocess from `WslOmniAsrProducer` | `test_adapter_identity.py:127`; `test_asr_worker_diagnostics.py` |
| `asr_resume` binding (273-337; device at 318) | identity passes through; LLM default `cuda:1` | `ResumableBackend` | `test_asr_resume.py` |
| `studio_host` champion stage (114-250) | fused descriptor and drift check | studio host process | `test_studio_host.py:154-300` |
| `pipeline.py` CLI (4854, 4862, 5263-5303, 5439-5453) | `--omni-asr-checkpoint` / env; mutual exclusion | CLI | `test_pipeline.py` refusal tables (around 3435, 3510, 5280) |
| `wsl_setup.py:1061` | message only | `wsl_setup` checks | `test_wsl_setup.py` |
| `asr_completion.py` | **no change** (same model class and generator); verified on hardware in T0 | `asr.py:892-893`; `asr_resume.py:293` | `test_asr_completion.py` (unchanged) |
| `omni_assets.py` | **no change** (the `assets=` subset already exists) | | `test_champion_held_assets.py` |
| `transcripts.py:544` | comment only (validation already accepts any string) | | `test_transcripts.py` |
| `asr_completion.py` (T8) | new pure `loop_suspect(text, seconds)`; beam variant of `require_natural_completion` (selected hypothesis must end on EOS); new `COMPLETION_POLICY_ID` | `asr.py:893` `transcribe_completed`; `asr_resume.py:24` policy ID | `test_asr_completion.py` (new cases); cache-reuse refusal tests |
| `asr.py:893` caller (T8) | suspect → one beam-5 retry of that segment → else `DecodeIncomplete`; per-segment `decode_mode` | `OmniAsrBackend` transcribe path | `test_asr.py` fake loop/complete generators |
| run report / transcript provenance (T8) | `decode_mode` and the retry count | `transcripts.py`, run report | `test_transcripts.py` |
| `DECISIONS.md` | new ADR D-xxx; T8 needs a separate ADR amending D-281 | | |
| `scripts/run-with-omniasr-paused.sh` | new operator wrapper | operator | new shell test |

## Found during implementation
Serena was not available; callers were mapped with grep and reading, as in research.md.

| Task | Symbol | Change | Callers / consumers | Tests |
|---|---|---|---|---|
| T1 | `OmniAsrBackend._load_adapted_llm` | non-PEFT half extracted to `_load_trainer_7b` (same calls, same order) | `_load`; new `_load_fused_llm` | `test_champion_consumers_receive_held_assets`, `test_champion_config_failure_does_not_change_shared_constructor` |
| T1 | `OmniAsrBackend._load_ctc` | holds assets through `_open_held_assets` (CTC + tokenizer only when fused) | `align_segment` | `test_fused_load_holds_only_ctc_and_tokenizer` |
| T1 | `omni_assets._open_regular_nofollow`, `_hash_open_stream` | unchanged; now also used by `asr._held_fused_checkpoint` | `open_verified_omni_assets` | `test_held_fused_checkpoint_*` |
| T1 | `omni_assets.FUSED_CHECKPOINT_ASSETS` (new), `FusedCheckpointAsset` | code allowlist beside `OMNI_ASSETS`; the only fused admission authority (no `SHA256SUMS`) | `asr.fused_checkpoint_asset` (host identity, factory, resolver, studio host), `asr._held_fused_checkpoint` (worker bytes) | `test_the_code_allowlist_names_exactly_the_reviewed_v12_checkpoint`, `test_sha256sums_alone_does_not_authorise_a_fused_checkpoint` |
| T2 | `OmniAsrProducer.__init__` | `fused_checkpoint` keyword, refused beside a supplied backend | `create_omni_asr_producer` | `test_fused_identity_agrees_across_native_and_bridge_producers` |
| T2 | `asr_worker.run_request` | `fused_checkpoint` request field, `fused:` identity, crossed/both refusals | WSL worker `main` | `test_worker_refuses_foreign_or_impersonating_fused_identity` |
| T3 | `studio_host.capture_studio_deployment` | champion record and drift check through `_studio_champion`; LoRA record bytes unchanged | `load_studio_host_authorization`, `prepare_studio_host_transport` | `test_host_admission_*` (existing), `test_host_admission_records_a_fused_champion`, `test_host_admission_refuses_fused_champion_drift` |
| T3 | `pipeline._build_and_run` | two new argv refusals; champion resolution adds the fused route | `main`, durable workflow step | `_REFUSAL_CASES`, `_CLI_PREFLIGHT_CASES` and their bidirectional source scans |
| T4 | `QwenSoraniValidator.__init__`, `asr_resume.worker_journal` | defaults read `DEFAULT_ASR_DEVICE` | worker validator factory; worker journal binding | `test_stage_1_defaults_to_gpu_1_only` |
| T5 | `asr_worker.run_request` | `assert_gpu_headroom` before loading, real backend only | WSL worker `main` | `test_worker_checks_gpu_headroom_before_loading_the_real_backend`; injected-backend tests unaffected |
| T8 | `SegmentTranscript` | `decode_mode`, `retry_reason` (defaults keep positional callers) | every backend and test double; `asr_resume._segment` (accepts legacy four-field records) | `test_checkpoint_survives_abrupt_process_exit` (unchanged) |
| T8 | `_validate_hard_segments`, `_assemble_canonical_transcript` | carry decode provenance through validator corrections into `SegmentConfidence` | both producers, worker | `test_retry_provenance_reaches_the_artifact_and_greedy_bytes_do_not_change` |
| T8 | `RawTranscript.to_json` / `from_json` | greedy segments omit the two keys (bytes unchanged) | transcript store, worker output, host reader | `test_transcripts.py` (unchanged) |
| T8 | `PipelineRun.to_dict` | `beam5_retries` count | run report | `test_retry_provenance_reaches_the_artifact_and_greedy_bytes_do_not_change` |
| T8 | `test_asr_completion.CompletionBackend` | gains `_transcribe_llm_beam` so the both-loop halt is exercised | its two tests | `test_alignable_repetition_stop_is_refused_before_alignment`, `test_incomplete_decode_stops_worker_before_later_segments` |

VEX binding of the fused asset (control audit, 2026-10-14): `FUSED_CHECKPOINT_ASSETS` sits beside
`OMNI_ASSETS` in `omni_assets.py`, but is deliberately *not* added to the WSL runtime receipt,
`_parse_runtime_payload`, the probe or `tests/test_vex.py`. Those consume `OMNI_ASSETS` through
`provision_omni_assets`, which downloads each asset from its HTTPS URL into fairseq2's cache;
the fused file has no URL and is operator-supplied, so including it there would need a new
provisioning step and would change the receipt's three-asset/43,546,500,168-byte checks and VEX
`applicability.assets`. That, and rewriting the D7/D8 VEX justifications, is owner work;
`security/wsl-asr-vex.json` is not edited here.
