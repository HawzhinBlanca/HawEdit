# EARS Acceptance

These requirements implement BLUEPRINT §§2-5, D-263, D-274 and extend §§8.1-8.3/AC-1-AC-12.
Named regressions below are planned until executed in the canonical gate; names are not
test-result claims. Human acceptance remains independent evidence, not a unit-test proxy.

Pure preparation/projection tests prove those adapter boundaries only. Their names do not
prove queued producer execution, durable token persistence, frontend adoption or authenticated
delivery; system criteria remain unaccepted until the complete integration and CI are evidenced.

| ID | Criterion | Named evidence |
|---|---|---|
| U1 | WHEN supported video bytes are uploaded, THE studio SHALL finalize a probed immutable source under an opaque ID. | test_upload_finalizes_real_media_bytes |
| U2 | WHEN upload bytes are truncated, over limit, invalid or interrupted, THE studio SHALL refuse a runnable source and report a contextual error. | test_upload_refuses_truncated_or_invalid_media |
| U3 | WHEN different files share a name, THE studio SHALL retain distinct content-bound sources. | test_upload_duplicate_names_are_isolated |
| U4 | WHEN persisted upload fields or HTTP length headers are malformed, THE studio SHALL issue a contextual refusal without publishing a source or relaxing parser safety limits. | test_upload_malformed_record_fields_are_contextual_refusals; test_upload_http_extreme_content_length_is_a_refusal |
| U5 | WHEN an upload response or final ticket write is lost, THE studio SHALL recover the same source ID only after verifying committed metadata and bytes, distinguish live from interrupted transfers, and expose recovery failure without inventing success. | test_upload_status_recovers_lost_response; test_upload_status_recovers_committed_media_after_ticket_failure; test_upload_status_refuses_mismatched_committed_evidence; test_upload_status_distinguishes_live_and_interrupted_transfer; test_upload_http_status_is_guarded_and_contextual |
| J1 | WHEN a generation request uses an unsupported option or raw server path, THE studio SHALL refuse it before model work. | test_studio_rejects_paths_and_unsupported_options |
| J2 | WHEN a request is accepted, THE studio SHALL resolve effective presets and construct producers through build_parser/build_and_run. | test_studio_uses_shared_producer_configuration |
| J3 | WHEN an idempotency token is reused with different content, THE studio SHALL return conflict; identical retries SHALL reuse durable identity. | test_studio_idempotency_is_content_bound |
| J4 | WHEN a job renders private candidates, THE studio SHALL await review and SHALL NOT claim completed publication. | test_studio_render_is_not_completed_publication |
| J5 | WHEN a stage emits start, complete, skip or billing events, THE studio SHALL preserve event state/sequence without invented work percentages. | test_studio_progress_preserves_event_state |
| D1 | WHEN the process restarts or storage fails, THE studio SHALL retain recoverable work and expose uncertainty/diagnostics. | test_studio_restart_and_persistence_failure_are_visible |
| D2 | WHEN an old job claims completion without current verification, THE studio SHALL preserve it as unverified historical data. | test_studio_migrates_legacy_completion_without_publishing |
| D7 | WHEN historical job records are malformed, linked, unavailable or changed after startup, THE studio SHALL expose bounded fresh diagnostics without mutating originals or inventing an empty complete history. | test_studio_history_malformed_records_are_visible; test_studio_history_refuses_links; test_studio_history_limits_and_storage_are_visible; test_studio_history_http_refresh_reads_disk |
| D8 | WHEN a historical record claims running or queued work, THE studio SHALL mark recovery reconciliation required without automatic re-execution or fabricated progress. | test_studio_history_abandoned_work_requires_reconciliation |
| D9 | WHEN JSON request depth exceeds the native decoder limit within the body ceiling, THE studio SHALL return contextual refusal without raising recursion limits or dropping the response. | test_studio_json_depth_refusal_is_contextual |
| R3 | WHEN the old caption endpoint cannot create an immutable measured render revision, THE studio SHALL refuse the edit without modifying metadata, media or canonical ASR. | test_studio_legacy_caption_edit_refuses_without_mutation |
| D3 | WHEN durable submission crosses the request-ledger and DBOS boundary, THE studio SHALL commit immutable token/content identity before enqueue and reconcile uncertain enqueue with the same workflow ID. | test_studio_submission_tokens_survive_reconstruction; test_studio_queue_recovers_lost_acknowledgement |
| D4 | WHEN studio workflows are queued, THE studio SHALL enforce persisted global and worker concurrency one and reuse completed duplicate identity without re-executing it. | test_studio_queue_runs_serially_and_reuses_completed_work; test_studio_queue_refuses_conflicting_limits |
| D5 | WHEN a studio model request may incur billing, THE guarded transport SHALL commit bound intent and conservative budget reservation before egress, preserve uncertain outcomes without replay, and return confirmed responses only after durable persistence. | test_studio_billing_response_loss_refuses_replay; test_studio_billing_storage_failures_are_atomic; test_studio_billing_process_crash_after_response_refuses_replay; test_studio_billing_expiry_during_count_prevents_generation |
| D6 | WHEN repeated discovery passes use identical content, THE studio SHALL preserve distinct call occurrences and replay each confirmed occurrence without collapsing K votes into one call. | test_studio_billing_repeated_content_preserves_occurrences |
| J6 | WHEN a trusted guarded transport is supplied, THE shared builder SHALL route both discovery and judging through the same injected client without changing default CLI/durable construction. | test_studio_builder_routes_discovery_through_injected_transport; test_studio_builder_routes_judging_with_real_frames_through_injected_transport |
| A1 | WHEN media is requested, THE studio SHALL serve only job/clip manifest-listed artifacts with bounded range playback and refuse unlisted filesystem routes. | test_studio_artifact_scope_and_ranges; test_studio_refuses_unlisted_filesystem_routes |
| A2 | WHEN GET or HEAD names an unlisted filesystem path or unscoped historical media URL, THE studio SHALL refuse it without directory enumeration or byte disclosure. | test_studio_refuses_unlisted_filesystem_routes; test_studio_unscoped_media_is_refused |
| A3 | WHEN a private preview is served, THE studio SHALL bind the job/clip manifest, measured hash/size/duration and exact response snapshot, refusing links, escapes, corruption and changed bytes. | test_studio_preview_refuses_changed_evidence; test_studio_preview_snapshot_survives_source_change; test_studio_preview_refuses_links |
| A4 | WHEN the protected producer worker or verified publication is absent, THE status endpoint SHALL report the missing capability and unknown latest deliverable without fabricated quality or duration. | test_studio_status_never_fabricates_readiness_or_reel |
| A5 | WHEN the dashboard loads offline, THE studio SHALL serve its shipped digest-bound font without an external font request. | test_studio_local_font_is_pinned_and_offline |
| A6 | WHEN the studio font is packaged or resolved from installed data, THE system SHALL retain the original digest, distribute its copyright/licence/provenance and identify it separately in the SBOM; missing or altered checkout assets SHALL refuse without fallback. | test_studio_font_packaging_and_sbom_cover_actual_font; test_studio_font_installed_record_and_missing_source_are_verified |
| R1 | WHEN approval signatures or bound bytes are stale/invalid, THE studio SHALL refuse publication. | test_studio_approval_rejects_invalid_signature_and_changed_bytes |
| R2 | WHEN burned-in content changes, THE studio SHALL create/measure an immutable revision, preserve canonical ASR and invalidate approval. | test_studio_caption_edit_renders_new_revision |
| UI1 | WHEN a creator uses the complete flow at required sizes or keyboard/zoom, THE studio SHALL expose accessible controls, truthful context and recoverable errors. | test_studio_semantic_controls_and_no_fabricated_quality; browser/NVDA evidence |
| UI2 | WHEN the studio opens without a selected source/job or protected worker, THE studio SHALL show an empty selected-job context, unavailable generation and unknown measurements without fabricated completed stages. | test_studio_semantic_controls_and_no_fabricated_quality; fresh browser evidence |
| UI3 | WHEN a creator uploads a browser-selected file, THE studio SHALL send its actual bytes through the reservation/PUT contract, distinguish transfer from media validation and recover uncertain responses without inventing a source. | test_studio_ui_upload_and_submission_contract; native upload regressions; browser upload evidence |
| UI4 | WHEN a submission result is uncertain, THE studio SHALL retain the exact source/options/client token for reconciliation and SHALL NOT silently submit a changed request under new identity. | test_studio_ui_persists_bound_submission_before_egress; browser recovery evidence |
| UI5 | WHEN selected historical jobs/candidates change or reads fail, THE studio SHALL clear obsolete media/measurements, show unverified historical context and expose recoverable scoped preview errors without presenting private copies as published export. | test_studio_ui_history_and_preview_are_explicit; fresh browser evidence |
| E1 | WHEN a candidate verdict is computed, THE acceptance system SHALL derive claims from current verified evidence, report failures and respect episode/reviewer dependence. | current-SHA independent study and scorecard regressions |
| E2 | WHEN every frozen threshold and AC obligation is met after 30 days and fresh holdout, THE release SHALL require authenticated owner/editor approval before 10/10. | signed sustained acceptance packet |
## Private Billing Storage Adoption

- PS1: WHEN a billed transport selects a journal path, THE supervisor SHALL create a
  missing leaf privately or refuse an existing nonprivate root before opening SQLite or
  sending any upstream data, preserving existing bytes and permissions.
  Tests: test_studio_billing_private_root_required_before_any_egress,
  test_studio_private_new_journal_is_owner_private.
- PS2: WHEN a journal path or SQLite sidecar is linked, nonregular, orphaned or outside
  its bound namespace, THE supervisor SHALL refuse without modifying that evidence.
  Tests: test_studio_billing_linked_database_refused,
  test_studio_private_linked_sidecars_refused,
  test_studio_private_orphan_sidecars_preserved.
- PS3: WHEN bound root/database identity or access changes, THE supervisor SHALL refuse
  before further upstream calls and SHALL NOT return a private model response as confirmed.
  Tests: test_studio_billing_database_replacement_during_count_refuses_generation,
  test_studio_billing_root_replacement_after_response_retains_uncertainty.
- PS4: WHEN valid private journal storage is restarted after a real abrupt response loss,
  THE supervisor SHALL preserve the original intent and refuse blind rebilling.
  Tests: test_studio_billing_process_crash_after_response_refuses_replay,
  test_studio_private_real_wal_crash_recovers_without_deleting_evidence.
- PS5: WHEN original schema/budget/response/replay tests use private journals, THE
  supervisor SHALL retain their existing refusal, arithmetic and K-occurrence contracts.
  Tests: existing complete test_studio_billing.py suite; no earlier assertion is weakened.
- PS6: WHEN a selected filename or directory component would be normalized into an
  ambiguous local path, THE supervisor SHALL refuse before creating any storage.
  Tests: test_studio_private_nonportable_names_refused,
  test_studio_private_parent_normalization_refused.

## Private Upload And Outbox Adoption

- PS7: WHEN an upload root/member is unsafe or replaced, THE studio SHALL refuse before
  reading/writing/publishing outside its bound private namespace.
  Tests: test_studio_upload_shared_root_is_preserved_and_refused,
  test_studio_upload_linked_ticket_is_preserved,
  test_studio_upload_container_replacement_refuses.
- PS8: WHEN transfer failure follows namespace substitution, THE studio SHALL preserve
  unrelated original bytes and SHALL NOT acknowledge a runnable source.
  Test: test_studio_upload_failure_cleanup_cannot_follow_replaced_staging.
- PS9: WHEN private metadata is atomically written, THE storage SHALL retain actual
  owner/access policy and refuse unsafe prior targets without altering their bytes.
  Tests: test_studio_private_atomic_metadata_is_private,
  test_studio_private_atomic_metadata_refuses_linked_target.
- PS10: WHEN submission storage is lost/replaced, THE outbox SHALL refuse without
  recreating the main file, losing the token or fabricating dispatch confirmation.
  Tests: test_studio_submission_missing_database_is_not_recreated,
  test_studio_submission_shared_root_is_preserved_and_refused.
- PS11: WHEN old module-qualified storage errors are restored, THE system SHALL retain
  public catcher compatibility without a circular import.
  Test: test_studio_storage_error_preserves_legacy_pickle_and_catchers.
- PS12: WHEN media bytes use a container incompatible with their supported filename,
  THE studio SHALL refuse a runnable source while preserving original external bytes;
  WHEN a supported container decodes, THE studio SHALL retain the exact uploaded bytes.
  Tests: test_studio_upload_refuses_mismatched_container,
  test_studio_upload_refuses_external_playlist_container,
  test_studio_upload_accepts_actual_supported_containers.
- PS13: WHEN upload storage is unconfigured or lost, THE HTTP API SHALL report storage
  unavailability without recreating public state or returning a runnable source.
  Tests: test_studio_http_unconfigured_upload_storage_refuses,
  test_studio_http_lost_upload_root_refuses_without_recreation.
- PS14: WHEN the native server starts, THE studio SHALL initialize privately at the
  local configured/default root and finalize actual uploaded bytes there.
  Test: test_studio_native_server_uploads_use_private_startup_storage.

These contracts do not certify whole-studio authentication, paid execution, media
sandboxing, mount semantics, authenticated publication or independent acceptance.

## T8 Paired Comparison Contracts

PC1-PC7 in paired-comparison-plan.md are EARS requirements with named tests: distinct
A/B data, truthful unknown legacy measurements, strict duplicate/map/payload refusal,
requested Wilson confidence, no superiority from repeated descriptive votes and no
comparative preference converted to QC approval or invented watched time. They do not
certify sealed blinding, clustered inference, signed evidence or release.

## T8 Acceptance Authority Contracts

AG-1-AG-6 in acceptance-authority-plan.md are EARS requirements with named tests. Aggregate
counts, Boolean claims, names and claimed use days remain descriptive input, not verified
gate/CI/study/use evidence. Scope/sustained assertions, direct construction and visual
leadership helpers cannot authorize a release or rating. Validate direct count accounting,
finite proportions, exact Boolean types and frozen minimum sample/window floors; separate
reported checks/requested rating from verified fields. Label current reference uncertainty
and diagnostic inference rather than certifying episode/reviewer independence. This guard
does not satisfy the mandatory positive evidence-verification or real-study requirements.
