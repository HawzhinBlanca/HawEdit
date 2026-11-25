# Spec: fused-checkpoint drafting (v12)

EARS acceptance criteria. Each names the tests that cite it in `tasks.md`.

## T1 Fused loader
- WHEN a backend is given a fused checkpoint, THE backend SHALL load it through a direct
  `wav2vec2_llama`/`7b` card with vocabulary from the held canonical tokenizer and no PEFT.
  `test_fused_checkpoint_loads_trainer_7b_without_peft`
- WHEN the held tokenizer does not report 10288 ids, THE backend SHALL halt before any weights
  load. `test_fused_checkpoint_vocab_mismatch_halts_before_weights`
- WHEN both a fused checkpoint and a LoRA adapter are given, THE backend SHALL refuse.
  `test_fused_checkpoint_and_lora_adapter_are_mutually_exclusive`
- WHEN a fused backend loads, THE backend SHALL hold only CTC-3B and the tokenizer from the stock
  asset set. `test_fused_load_holds_only_ctc_and_tokenizer`
- WHEN a fused checkpoint's filename, exact size or SHA-256 is not on `FUSED_CHECKPOINT_ASSETS`,
  THE system SHALL halt before any loader; files beside it (`SHA256SUMS`) SHALL never admit it.
  `test_the_code_allowlist_names_exactly_the_reviewed_v12_checkpoint`,
  `test_sha256sums_alone_does_not_authorise_a_fused_checkpoint`,
  `test_fused_admission_refuses_unlisted_or_unsafe_paths`,
  `test_held_fused_checkpoint_refuses_bytes_off_the_allowlist`
- WHEN a fused checkpoint is allowlisted, THE identity SHALL be `fused:<allowlisted sha256>`, and
  the held bytes SHALL be hashed once per stat identity per process.
  `test_fused_identity_is_derived_from_the_allowlist`,
  `test_held_fused_checkpoint_hashes_once_per_stat_identity`

## T2 Identity
- WHEN any producer runs a fused checkpoint, THE identity SHALL be `fused:<allowlisted sha256>`.
  `test_fused_identity_agrees_across_native_and_bridge_producers`
- WHEN a worker request pairs a fused checkpoint with a `lora:` identity, a LoRA adapter with a
  `fused:` identity, both weights, or a stock request with any identity, THE worker SHALL refuse
  before inference. `test_worker_refuses_foreign_or_impersonating_fused_identity`
- WHEN a fused run crosses into WSL, THE request SHALL carry `fused_checkpoint` and its identity,
  and stock requests SHALL stay byte-identical.
  `test_the_wsl_request_carries_the_fused_checkpoint_across_the_boundary`,
  `test_fused_and_lora_producers_refuse_both_weights`,
  `test_missing_fused_checkpoint_is_refused_before_stage_0`

## T3 CLI and environment
- WHEN `--omni-asr-checkpoint` or `HAWEDIT_CHAMPION_CHECKPOINT` is combined with
  `--omni-asr-adapter` or `--stock-decoder`, THE CLI SHALL refuse before any work.
  `test_the_cli_refuses_a_combination_that_cannot_work`,
  `test_the_fused_champion_environment_refuses_a_second_decoder`
- WHEN `HAWEDIT_CHAMPION_CHECKPOINT` is set, THE resolver SHALL return it or halt; unset SHALL
  keep the LoRA default. `test_the_fused_champion_environment_selects_or_halts`
- WHEN the studio host admits a fused champion, THE descriptor SHALL bind its path, digest and
  kind and refuse drift. `test_host_admission_records_a_fused_champion`,
  `test_host_admission_refuses_fused_champion_drift`

## T4 GPU 1 only
- WHEN no device is configured, THE LLM, CTC and validator SHALL default to `cuda:1`.
  `test_stage_1_defaults_to_gpu_1_only`, `test_champion_consumers_receive_held_assets`

## T5 :8000 coordination
- WHEN a Stage 1 GPU has less free memory than required, THE worker SHALL halt naming that GPU
  before loading. `test_gpu_headroom_halts_naming_the_busy_gpu`,
  `test_worker_checks_gpu_headroom_before_loading_the_real_backend`
- WHEN the wrapped command fails, THE pause wrapper SHALL still restart the server and remove its
  own lock; it SHALL refuse an existing lock.
  `test_pause_wrapper_restores_the_server_when_the_command_fails`,
  `test_pause_wrapper_refuses_an_existing_maintenance_lock`

## T8 Loop guard
- WHEN a greedy segment lacks natural EOS, repeats a 1-4 word unit 4 times, or exceeds the text
  rate, THE backend SHALL re-decode that segment once with beam 5 and keep it only if it is clean.
  `test_loop_suspect_flags_a_unit_repeated_four_times`,
  `test_loop_suspect_admits_ordinary_text_and_the_ieee_acronym`,
  `test_loop_suspect_text_rate_threshold_and_override`,
  `test_suspect_greedy_segment_keeps_a_clean_beam_retry`
- WHEN the beam retry is suspect too, THE backend SHALL raise `DecodeIncomplete` naming the
  segment and both attempts. `test_segment_suspect_under_both_decodes_halts_naming_it`
- WHEN a greedy segment is clean, THE backend SHALL not retry and its artifact bytes SHALL not
  change. `test_clean_greedy_segment_is_unchanged_and_never_retried`,
  `test_retry_provenance_reaches_the_artifact_and_greedy_bytes_do_not_change`,
  `test_retry_provenance_survives_segment_origins_and_greedy_origin_bytes`
- WHEN the beam's selected hypothesis did not sample a natural EOS, THE observer SHALL refuse.
  `test_beam_observer_admits_a_selected_hypothesis_with_sampled_eos`,
  `test_beam_observer_follows_ancestry_to_the_selected_row`,
  `test_beam_observer_refuses_a_selected_row_still_decoding_at_the_limit`,
  `test_beam_observer_refuses_eos_that_a_compression_stop_could_have_forced`,
  `test_beam_observer_ignores_checks_inside_the_compression_window`,
  `test_beam_observer_refuses_a_greedy_configured_generator`,
  `test_contract_refusal_is_not_retried`
- WHEN a beam-5 retry runs and the LLM and CTC share one CUDA device, THE backend SHALL move
  CTC-3B to the CPU only for the retry after the segment's CTC forward has finished, SHALL always
  move it back, and SHALL halt with `DecodeIncomplete` if it cannot; on separate devices or for a
  greedy segment it SHALL not move CTC.
  `test_shared_device_beam_retry_parks_ctc_on_cpu_and_restores_it`,
  `test_separate_devices_never_move_ctc`, `test_failed_beam_retry_still_restores_ctc`,
  `test_ctc_that_cannot_return_to_its_device_halts_the_run`,
  `test_clean_greedy_segment_never_moves_ctc_and_its_bytes_do_not_change`
- WHEN a cache record carries the previous completion policy, THE store SHALL refuse it.
  `test_loop_guard_policy_refuses_single_beam_cache_records`
