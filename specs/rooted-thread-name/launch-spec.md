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

## Prepared-View Witness Criteria

- WHEN a witness is constructed, THE observer SHALL retain original stopped
  PID2 and PID1 task/root/mount evidence before image preparation.
  Test: test_rooted_launch_owner_reobserves_original_prepared_view.
- WHEN prepared rights arrive, THE observer SHALL require a fresh nonce,
  original PID1 kernel credentials, exactly three rights and sealed EOF.
  Test: test_rooted_launch_prepared_handoff_framing_refuses.
- WHEN root or namespace evidence is foreign, wrong-type, non-descendant,
  writable, non-procfs or not PID1's actual root/cwd, THE observer SHALL refuse.
  Test: test_rooted_launch_refuses_foreign_prepared_view.
- WHEN original PID2 resumes, exits or changes view before the join, THE
  observer SHALL refuse. Test: test_rooted_launch_prepared_worker_must_remain_held.
- WHEN original descriptor slots are substituted or reopened, THE observer
  SHALL refuse and SHALL NOT close foreign slots during cleanup.
  Test: test_rooted_launch_prepared_view_preserves_substituted_slots.
- WHEN a prepared observation repeats, THE observer SHALL recheck genuine
  kernel evidence without signalling, namespace joining or executing.
  Test: test_rooted_launch_prepared_view_is_not_execution_authority.
- WHEN observation deadlines are invalid or a sender stalls, THE observer
  SHALL refuse within the original finite lifetime.
  Test: test_rooted_launch_prepared_view_deadline_refuses.

No test above substitutes for actual copied SDK/worker fence/production release.
# Joined-Worker Kernel Observation

- WHEN the outside owner verifies a joined worker, THE observer SHALL require
  the retained original PID2 in the exact prepared user/mount/root/cwd, stopped,
  single-thread, untraced, NNP and with all five capability sets zero.
  Tests: test_rooted_launch_owner_reobserves_joined_original_worker,
  test_rooted_launch_joined_worker_damaged_transition_refuses.
- WHEN authenticated prepared evidence is absent or the worker has not joined,
  THE observer SHALL refuse without signalling or executing the worker.
  Test: test_rooted_launch_joined_observation_requires_actual_transition.
- WHEN joined observation repeats, THE observer SHALL recheck kernel evidence
  without leaking descriptors or granting release/fence/SDK authority.
  Test: test_rooted_launch_joined_observation_has_no_execution_authority.

This observation does not prove Landlock/seccomp policy or close inherited FDs;
those remain mandatory typed-launch checks before any copied execution.
Authenticated-handoff, original death and reopened descriptor refusals are also
covered by test_rooted_launch_joined_observation_requires_authenticated_handoff,
test_rooted_launch_joined_observation_refuses_dead_original_scope and
test_rooted_launch_joined_observation_preserves_substituted_description.
