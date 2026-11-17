# Protected ASR EARS

PA1 service: WHEN an original registered worker thread requests a comm write,
THE controller SHALL use only its genuine anchored leaf, retain worker readonly
proc/GPU policy and release no result before drain/final policy inspection.
WHEN the request targets a foreign thread, THE broker SHALL refuse exact EPERM
without descriptor injection. Named regressions:
test_rooted_controller_actual_cpu_comm_service_returns_fenced;
test_rooted_controller_actual_gpu_comm_service_returns_fenced;
test_rooted_controller_actual_gpu_elf_returns_fenced.

WHEN controller completion acknowledgment is absent or its kernel sender/frame
differs, THE native fixture SHALL refuse a GPU test pass even if the worker
already exited. Regressions: test_rooted_gpu_controller_missing_final_ack_is_not_a_pass;
test_rooted_gpu_controller_wrong_completion_frame_is_not_a_pass.

| Criterion | Proposed Named Test |
| --- | --- |
| WHEN the diagnostic controller runs, THE system SHALL retain its existing30s/64KiB/64birth/32request ceilings. | test_protected_asr_preserves_diagnostic_limits |
| WHEN a production request is admitted, THE host SHALL bind source, champion/config/runtime/security identities and finite resources before copied SDK release. | test_protected_asr_requires_live_complete_admission |
| WHEN GPU broker service runs, THE controller SHALL permit only existing registered comm operations and SHALL independently verify mandatory worker/final-controller policy without a broader proc grant. | test_protected_asr_gpu_controller_combined_policy |
| WHEN runtime/model/input bytes differ or the closure exceeds measured bounds, THE worker SHALL refuse before inference. | test_protected_asr_changed_image_or_input_refuses |
| WHEN a segment completes, THE worker SHALL send bounded typed evidence and THE host SHALL durably acknowledge its canonical checkpoint before resume. | test_protected_asr_checkpoint_ack_before_resume |
| WHEN bytes/sequence/identity/ack differ or an owner dies, THE system SHALL retain uncertain work, drain original members and refuse completion. | test_protected_asr_transport_corruption_and_owner_loss |
| WHEN canonical alignment or completion fails, THE pipeline SHALL preserve the failure and SHALL NOT invent timings/text or render a misleading candidate. | test_protected_asr_incomplete_alignment_refuses_reel |
| WHEN paid judging is used, THE host SHALL send transcript only and refuse before exceeding the existing totalUS$5 cap or on billing uncertainty. | test_protected_asr_transcript_only_cumulative_cap |
| WHEN a private ZAR proposal is rendered, THE system SHALL bind actual source/output clocks, canonical caption provenance and measured media; only authenticated unchanged reviewed bytes may publish. | test_protected_asr_private_candidate_is_not_publication |

Names are proposed, not passing tests. Real media and native-Sorani review are
required for speech/meaning/caption accuracy; synthetic tests cannot prove them.

## First PA1 Kernel Profile Unit

| Criterion | Implemented Regression |
| --- | --- |
| WHEN an original trusted controller fence is installed, THE Snapshot SHALL record the genuine installed filter count and verify its final stacked fence. | test_rooted_gpu_owned_controller_fence_preserves_final_verification; test_rooted_controller_final_filter_binds_original_installed_profile |
| WHEN the controller and GPU Landlock policies are combined, THE Snapshot SHALL prove exact Landlock and seccomp denials separately without changing the default profile. | test_rooted_gpu_controller_proves_landlock_and_seccomp_separately |
| WHEN an unregistered filter, replay or boolean profile is supplied, THE Snapshot SHALL refuse it as policy evidence. | test_rooted_gpu_unregistered_filter_cannot_change_default_policy_proof; test_rooted_gpu_controller_fence_cannot_be_installed_twice; test_rooted_gpu_controller_filter_identity_cannot_be_supplied_as_boolean |

These tests are diagnostic kernel-policy coverage, not full PA1 GPU servicing or
any production ASR/media acceptance claim. No ledger row is promoted here.
