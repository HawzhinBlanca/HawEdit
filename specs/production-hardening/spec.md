# Spec — production-hardening

EARS acceptance criteria. Every criterion maps to at least one named automated test; that name
is what gets cited when a ledger row is flipped.

Criteria are grouped by the brief's phase. A criterion marked **[merge]** is satisfied by code
that already exists on `origin/codex/production-readiness-20260809` and is preserved by the
merge; the test still has to be found in the report before the row flips. A criterion marked
**[new]** is work on neither branch.

## Phase 1 — one authoritative branch

- **AC-1.1 [merge]** WHEN the integration branch is built, THE repository SHALL contain every
  file listed in `plan.md` §A, unmodified in behaviour.
  → `test_the_codystem_enforcement_surface_survived_the_merge`,
    `test_the_adapter_and_the_validator_both_survive_the_worker_request`
- **AC-1.2 [merge]** WHEN `PipelineRun.skipped()` is called, THE system SHALL derive the stage
  set from `fields(self)` and not from a hand-written tuple (D-171).
  → `test_skipped_is_derived_from_the_dataclass_fields`
- **AC-1.3 [merge]** WHEN the embedding checkpoint has no pinned revision, THE system SHALL
  degrade to no-cache and complete the run, rather than raising (D-140).
  → `test_an_unpinned_checkpoint_degrades_to_no_cache_rather_than_aborting`
- **AC-1.4 [merge]** WHEN an embedding-cache record is written, THE key SHALL include
  `temporal_patch_frames`.
  → `test_a_different_patch_size_is_a_different_cache_record`

## Phase 2 — filesystem, privacy, delivery safety

- **AC-2.1 [merge]** WHEN a candidate id is used to form any filesystem path, THE system SHALL
  validate it as one safe path component, refusing traversal, separators, dot components,
  control characters, absolute paths and reserved device names.
  → `test_a_candidate_id_that_is_not_one_safe_component_is_refused_before_any_filesystem_op`
- **AC-2.2 [merge]** WHEN a rendered artifact's measured duration is shorter or longer than the
  requested clip beyond one frame, THE system SHALL refuse to publish it.
  → `test_an_over_long_encode_is_refused_so_trailing_source_footage_never_publishes`,
    `test_a_grossly_short_encode_is_refused`
- **AC-2.3 [merge]** WHEN a clip has `auto_pass=True` and `human_reviewed=False`, THE render
  gate SHALL refuse it.
  → `test_auto_pass_never_substitutes_for_human_review`
- **AC-2.4 [merge]** WHEN delivery is interrupted by a kill, a disk failure, a retry or a
  concurrent run, THE system SHALL never expose a delivery that appears complete.
  → `test_a_killed_delivery_leaves_no_publishable_bundle`,
    `test_a_concurrent_publisher_loses_with_bundle_already_exists`
- **AC-2.5 [merge]** WHEN keyframes are extracted, THE system SHALL use a private per-attempt
  directory, AND a cleanup failure SHALL be attached to the in-flight exception rather than
  replacing it.
  → `test_keyframes_use_a_private_per_attempt_directory`,
    `test_a_cleanup_failure_does_not_mask_the_primary_error`

## Phase 3 — untrusted model boundaries

- **AC-3.1 [merge]** WHEN a model reply is parsed, THE system SHALL require exact JSON
  containers and field types.
  → `test_a_verdict_that_is_not_an_object_is_refused`
- **AC-3.2 [merge]** WHEN a numeric field carries a bool, a numeric string, NaN or Infinity,
  THE system SHALL refuse it.
  → `test_true_is_not_a_hook_score`, `test_a_numeric_string_is_not_a_number`,
    `test_nan_and_infinity_are_refused`
- **AC-3.3 [new]** WHEN a verdict object carries a field the schema does not name, THE system
  SHALL refuse it.
  → `test_an_unknown_field_in_the_verdict_is_refused`
- **AC-3.4 [merge]** WHEN `countTokens` returns a negative or non-integer total, THE system
  SHALL refuse it.
  → `test_a_negative_token_count_is_refused`
- **AC-3.5 [merge]** WHEN a response body, an error message or a serialized `StageSkipped`
  reason is produced, THE system SHALL bound its length.
  → `test_an_oversized_response_body_is_truncated_at_the_cap`,
    `test_a_stage_skipped_reason_is_bounded`
- **AC-3.6 [merge]** WHEN a credential, auth or transport failure occurs, THE system SHALL
  raise a domain error and SHALL NOT send a request.
  → `test_unreadable_credentials_become_a_domain_error_with_no_request_sent`
- **AC-3.7 [merge]** WHEN one judge invocation runs, THE system SHALL issue at most one billed
  `generateContent` call, AND SHALL NOT retry an ambiguous billed request.
  → `test_one_judge_invocation_issues_exactly_one_billed_call`,
    `test_an_ambiguous_billed_result_is_not_retried`
- **AC-3.8 [merge]** WHEN any request is made, THE API key SHALL appear in no URL, log,
  exception or artifact.
  → `test_the_api_key_is_a_header_and_never_a_query_parameter`
- **AC-3.9 [merge]** THE Vertex and ZDR governance checks SHALL remain in force.
  → `test_governance_refuses_an_ungoverned_vertex_project` (existing; unchanged both branches)

## Phase 4 — model supply chain and readiness

- **AC-4.1 [merge]** WHEN a checkpoint is provisioned, THE system SHALL require an exact
  40-hex revision and a byte manifest, and SHALL verify digests with no-follow, regular-file,
  reparse and hardlink defenses.
  → `test_a_checkpoint_without_a_pinned_revision_is_refused`,
    `test_a_hardlinked_member_is_refused`, `test_a_reparse_point_member_is_refused`
- **AC-4.2 [merge]** WHEN a checkpoint is published, THE system SHALL stage privately and
  publish by atomic no-replace rename, AND SHALL re-verify the final path before reporting
  success.
  → `test_publication_refuses_to_replace_an_existing_final_path`,
    `test_the_final_path_is_verified_after_publication`
- **AC-4.3 [merge]** WHEN a fetch is interrupted by an exception, Ctrl-C or process death, THE
  system SHALL resume rather than restart or publish a partial checkpoint.
  → `test_a_keyboard_interrupt_preserves_the_resume_directory`
- **AC-4.4 [merge]** WHEN a checkpoint is loaded, THE verify-to-load binding SHALL be held
  through configuration parsing and every `from_pretrained` call.
  → `test_the_verified_lock_is_held_across_from_pretrained`
- **AC-4.5 [merge]** WHEN a config requests remote code, THE system SHALL refuse it.
  → `test_trust_remote_code_anywhere_in_the_config_is_refused`
- **AC-4.6 [merge]** WHEN a model directory is junk or partial, or a package, asset or CUDA is
  missing, THE readiness report SHALL say unavailable, AND the status command SHALL exit
  nonzero.
  → `test_a_partial_checkpoint_reports_unavailable`,
    `test_the_status_command_exits_nonzero_when_a_requested_component_is_unavailable`
- **AC-4.7 [merge]** WHEN WSL is consuming a checkpoint, THE host SHALL NOT publish over it.
  → `test_the_host_publisher_blocks_while_wsl_holds_the_lease`
- **AC-4.8 [merge]** WHEN a model root, staging root or lock file has an unsafe owner, ACL,
  mode or reparse point, THE system SHALL refuse it.
  → `test_a_world_writable_model_root_is_refused`, `test_a_lock_file_that_is_not_regular_is_refused`

## Phase 5 — GPU lifecycle

- **AC-5.1 [merge]** WHEN the visual phases run, THE system SHALL release each component before
  the next loads, in the order embedder → reranker → VideoChat3 reader → TimeLens grounder, AND
  frame pixels SHALL be deleted last.
  → `test_the_release_order_is_embedder_then_reranker_then_reader_then_grounder`
- **AC-5.2 [merge]** WHEN cleanup fails, THE failure SHALL NOT mask the primary error.
  → `test_a_release_failure_does_not_mask_the_primary_error`
- **AC-5.3 [merge]** WHEN an adapter is reused after release, THE system SHALL lazily reload.
  → `test_a_released_reader_reloads_on_next_use`
- **AC-5.4 [merge]** WHEN TimeLens loads, no earlier visual model SHALL remain resident.
  → `test_timelens_does_not_load_while_earlier_visual_models_are_resident`

## Phase 6 — dependencies and release

- **AC-6.1 [merge]** THE declared Python support SHALL be `>=3.11,<3.13`.
  → `test_the_declared_python_support_is_bounded`
- **AC-6.2 [merge]** THE host, model-fetch, GPU and WSL ASR environments SHALL install from
  full hash locks, AND the installed inventory SHALL match the lock exactly.
  → `test_every_lock_pins_one_hash_per_distribution`,
    `test_an_extra_installed_distribution_fails_the_inventory_audit`
- **AC-6.3 [merge]** EVERY GitHub Action SHALL be pinned by full commit SHA.
  → `test_every_action_is_pinned_by_full_sha`
- **AC-6.4 [merge]** THE build job SHALL be unprivileged and separate from the OIDC/attestation
  job, AND release SHALL be bound to a successful exact-SHA canonical gate.
  → `test_the_build_job_has_no_id_token_permission`,
    `test_release_refuses_a_gate_run_whose_head_sha_differs`
- **AC-6.5 [merge]** THE wheel SHALL be built from immutable git objects in two independent
  trees and compared for reproducibility.
  → `test_two_source_trees_produce_one_wheel_digest`
- **AC-6.6 [merge]** THE wheel SHALL pass a fresh installed smoke on 3.11 and 3.12 with no
  import from the checkout.
  → `test_the_smoke_job_does_not_check_out_the_repository`
- **AC-6.7 [merge]** THE attested and uploaded artifact sets SHALL be identical, AND release
  SHALL refuse before builders or output directories are created when evidence is invalid.
  → `test_the_attested_and_uploaded_sets_are_identical`,
    `test_release_refuses_before_creating_the_output_directory`

## Phase 7 — structured failure reporting

- **AC-7.1 [merge]** WHEN an operational failure occurs in ASR, Path A, visual
  extraction/inference, keyframes, Gemini, TimeLens, tracking, render or delivery, THE system
  SHALL produce a bounded, JSON-serializable `StageSkipped` record.
  → `test_every_operational_stage_failure_becomes_a_serializable_stage_skipped`
- **AC-7.2 [merge]** THE system SHALL NOT catch `AssertionError` or arbitrary programmer
  defects.
  → `test_an_assertion_error_is_not_swallowed_as_an_operational_failure`
- **AC-7.3 [merge]** WHEN `--json` is given, THE CLI SHALL emit valid JSON on stdout, keep
  stderr empty for expected operational absence, exit 1 for an incomplete run, and retain exit 2
  for malformed static arguments or configuration.
  → `test_json_output_is_valid_and_stderr_is_empty_for_an_expected_absence`,
    `test_an_incomplete_run_exits_1`, `test_a_malformed_argument_still_exits_2`

## Out of scope

Anything requiring a credential, a licence acceptance, a live benchmark or human evaluation.
Per the brief's final rule, the system is not to be labelled complete while any of those remain
unavailable — `BLOCKED.md` #1 (labelled Sorani set), #3 (Gemini credentials) and #4 (pyannote
gated) are all live.
