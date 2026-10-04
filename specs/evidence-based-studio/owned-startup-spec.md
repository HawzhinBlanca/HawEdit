# Owned Startup EARS

Approved parent T3, BLUEPRINT sections2-5, D-276. Mechanism only; no production, review,
billing, replay, quality or publication authority follows from launch success.

| ID | Requirement | Named automated evidence |
|---|---|---|
| OS1 |WHEN a protected supervisor starts, THE studio SHALL acquire and retain an owner-private native cross-process lease before database bootstrap or runtime launch, refusing contention/substitution without truncating or deleting the lock or original work.|test_native_lease_contends_across_processes_and_releases_after_exit,test_lease_refuses_changed_binding_and_preserves_members|
| OS2 |WHEN a DBOS instance, registry or ambient override is foreign, THE studio SHALL refuse startup before launch/migration/deserialization and SHALL NOT destroy or overwrite that state.|test_owned_runtime_refuses_foreign_singleton_without_destroying_it,test_owned_runtime_refuses_foreign_registry_before_storage_mutation,test_owned_runtime_refuses_ambient_overrides|
| OS3 |WHEN the bound journal is empty, THE owned studio SHALL bootstrap the exact pinned publisher transactionally and admit it before launch; WHEN existing data is foreign/damaged, THE studio SHALL preserve it and refuse before DBOS deserialization or migration.|test_owned_runtime_bootstraps_actual_pinned_database,test_owned_runtime_refuses_bad_existing_journal_before_launch,test_bootstrap_ddl_rolls_back_on_process_exit|
| OS4 |WHEN DBOS reads or commits journal data, THE studio SHALL inspect the exact same native SQLite transaction against existing bounded portable schema/outbox policy, refusing unknown tags, altered inputs, attachments/temp objects or uncommitted unsafe writes before deserialization or commit.|test_same_connection_inspection_sees_uncommitted_data_without_ending_transaction,test_same_connection_inspection_refuses_other_database_and_attachments,test_owned_engine_refuses_unsafe_uncommitted_commit,test_owned_engine_refuses_changed_raw_rows_before_getter|
| OS5 |WHEN the owned DBOS runtime launches, THE studio SHALL verify actual engine/serializer/config/registry identities with serial queue1/1, disabled admin/OTLP and no foreign pollers/cloud, retaining the source-bound version and exact ID-only workflow contract.|test_owned_runtime_launches_actual_serial_queue_and_preserves_cli,test_owned_runtime_refuses_runtime_identity_drift|
| OS6 |WHEN shutdown is requested, THE studio SHALL stop new dispatch, bound draining, retain storage lease/engine while any captured worker/background/connection remains live, and only destroy its own runtime and release after actual quiescence.|test_shutdown_retains_lease_until_real_worker_exits,test_shutdown_refuses_held_engine_connection,test_owned_runtime_closes_only_its_own_resources|
| OS7 |WHEN a supported immutable inert job is resumed or submitted twice, THE owned studio SHALL recover through the same guarded runtime and immutable outbox identity without duplicate execution for confirmed results; WHEN unsupported persisted work exists, THE studio SHALL refuse rather than execute or omit it.|test_owned_runtime_duplicate_dispatch_executes_once,test_owned_runtime_recovers_actual_pending_job_after_process_exit|

Additional existing132 raw admission and caller regressions remain required, including NUL
projection, bounded budgets, unsupported serialized surfaces, actual publisher/inert workflow
controls and original data preservation. Canonical gate plus same-SHA CI precede ledger
promotion. Browser/creator/model/revision/export and sustained acceptance are separate.

OS5/OS6 resource correction: the actual pinned database and OptionEngine must be captured
after direct owned-base proxy proof, not pool equality. Replacement/loss refuses before
shutdown flags change and retains the lease. Named native regression:
test_owned_runtime_refuses_unowned_database_resources (engine/proxy/database/missing).
Research, actual caller map and red/green diagnostics are in owned-resource-plan.md and
owned-resource-verification.md; no production authority follows from these mechanics.

Additional named OS2/4/6 evidence: test_owned_runtime_refuses_real_foreign_constructor_race_without_mutation;
test_same_connection_refuses_custom_decoders_before_queries;
test_same_connection_inspection_preserves_vm_handler_and_connection_policy;
test_owned_runtime_storage_contention_is_bounded_without_library_retry. Draining dispatch
refusal SHALL retain the same immutable submission identity and persist an actionable
diagnostic, or expose diagnostic persistence failure;
test_draining_refuses_new_dispatch_without_losing_reserved_job covers the real refusal.
