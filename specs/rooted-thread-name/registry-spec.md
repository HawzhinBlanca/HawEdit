# Original Registry EARS

Named regressions; implementation evidence is recorded in registry-research.md.
Unimplemented broker/default/copy-runtime rows remain proposed, not gate claims.

| Criterion | Named Regression |
| --- | --- |
| WHEN an original worker or thread is born/stopped by a real kernel event, THE registry SHALL anchor its original task before any SDK resumption. | test_original_registry_anchors_kernel_birth_before_resume |
| WHEN a caller supplies a foreign, late-discovered or unregistered numeric target, THE broker SHALL refuse without injecting a descriptor. | test_original_registry_refuses_unregistered_or_foreign_target |
| WHEN a registered task description is replaced or reopened, THE registry SHALL refuse and SHALL NOT close the substituted foreign handle. | test_original_registry_refuses_substituted_task_description |
| WHEN a registered task exits or its number is reused, THE broker SHALL refuse its old identity and SHALL NOT adopt the replacement. | test_original_registry_refuses_exited_or_reused_task |
| WHEN the controller attempts other ptrace operations or targets, THE kernel SHALL refuse; approved event observation SHALL NOT rewrite worker state or syscall results. | test_original_registry_kernel_refuses_unapproved_trace_requests |
| WHEN a traced original member exits, THE controller SHALL reap every original member within the bound rather than wait only for the main task. | test_original_registry_drains_all_original_members |
| WHEN an approved exact comm notification arrives, THE broker SHALL use its copied request and genuine original anchored descriptor through atomic ADDFD_SEND. | test_original_registry_broker_renames_only_registered_target |
| WHEN no command/broker is enabled, THE snapshot SHALL retain every existing default isolation and refusal. | test_original_registry_default_preserves_snapshot_refusals |
| WHEN a copied interpreter/SDK refuses, THE command SHALL retain that refusal and SHALL NOT claim model/producer/video readiness. | test_original_registry_copied_runtime_refusal_is_not_admission |
| WHEN original PID2 genuinely execs a sealed executable, THE registry SHALL observe the kernel exec event without rewriting state or changing the original group identity. | test_original_registry_anchors_actual_exec_without_state_rewrite |
| WHEN many original threads start together, THE registry SHALL anchor their kernel births before resumption and reap the complete group. | test_original_registry_drains_burst_threads_from_kernel_births |
| WHEN a registered primary task slot is closed, THE registry SHALL refuse its use and preserve only independently held original cleanup authority. | test_original_registry_closed_task_slot_is_not_close_authority |
