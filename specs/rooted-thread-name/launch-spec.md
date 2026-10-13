# Stopped-Worker Launch EARS

Proposed named tests, not existing passes or admission evidence.

| Criterion | Named Regression |
| --- | --- |
| WHEN image preparation begins, THE launch SHALL already hold authenticated original PID1/PID2 and parent-death/cancellation lifetime before any copied SDK release. | test_rooted_launch_original_owner_precedes_preparation |
| WHEN initial privileges differ from Snapshot's allowed preparation boundary, THE launch SHALL refuse rather than retain model capabilities or alter UID mapping rules. | test_rooted_launch_preserves_preparation_capability_order |
| WHEN a supplied prepared namespace/root handle is foreign, reopened, wrong-type or non-descendant, THE worker SHALL refuse before joining or SDK exec. | test_rooted_launch_refuses_foreign_prepared_view |
| WHEN the original prepared view is re-observed, THE owner SHALL derive its transition binding from original kernel handles rather than affirmative flags or numeric discovery. | test_rooted_launch_owner_reobserves_original_prepared_view |
| WHEN copied SDK execution starts, THE worker SHALL already have readonly root/proc, zero caps, NNP, mandatory Landlock, namespace/ptrace/process/foreign-handle refusals and the genuine listener before stronger errno rules. | test_rooted_launch_worker_fenced_before_actual_exec |
| WHEN command configuration contains a callback, unlisted executable, shell string or unbounded argv/environment, THE launch SHALL refuse before execution. | test_rooted_launch_refuses_nonmanifest_command |
| WHEN the owner dies or a member/IO/listener/timer becomes uncertain, THE launch SHALL cancel via original handles, drain all members and refuse successful completion. | test_rooted_launch_owner_death_and_uncertain_drain |
| WHEN Snapshot construction returns after a typed command, THE controller SHALL satisfy the existing final policy/inspection contract and SHALL NOT return unfenced. | test_rooted_launch_controller_fenced_before_return |
| WHEN no command is selected, THE Snapshot SHALL retain all existing default isolation/refusals. | test_rooted_launch_default_contract_unchanged |
| WHEN a genuinely copied interpreter/Torch cannot start or compute, THE launch SHALL preserve the real refusal and SHALL NOT claim ASR/video readiness. | test_rooted_launch_copied_runtime_refusal_is_not_readiness |

Meaningful source unit: whole caller cohorts + exact canonical gate + same-SHA
CI before completion. No model inference or video acceptance from kernel tests.

## Initial RT2A Automated Criteria

- WHEN preparation readiness is checked, THE Scope SHALL require kernel-bound
  original PID1 and stopped PID2 before copying, without releasing either.
  Tests: test_rooted_launch_original_owner_precedes_preparation,
  test_rooted_launch_preparation_has_no_release_authority.
- WHEN identities, namespace views, capabilities, NNP, member count or worker
  state are invalid, THE Scope SHALL refuse while retaining original stop.
  Test: test_rooted_launch_invalid_preparation_boundary_refuses.
- WHEN a creator is concurrent or the scope closed, THE Scope SHALL refuse.
  Tests: test_rooted_launch_preparation_refuses_multithread_creator,
  test_rooted_launch_preparation_refuses_closed_scope.
- WHEN deadline configuration is invalid or exceeds30seconds, THE Scope SHALL
  refuse. Test: test_rooted_launch_preparation_invalid_deadline_refuses.
- WHEN readiness is checked repeatedly, THE Scope SHALL preserve original
  bounding capabilities and SHALL NOT leak acquired kernel descriptors.
  Test: test_rooted_launch_preparation_retains_bounding_caps_without_fd_leaks.

These tests do not satisfy the separate prepared-view, actual-exec or full-video
criteria above. All task rows remain unchecked.
