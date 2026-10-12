# Proposed EARS Criteria

All test names are proposed and currently unevidenced.

| Criterion | Required Named Test |
| --- | --- |
| WHEN the original registered worker requests its live original thread's exact comm leaf, THE broker SHALL inject only a genuine anchored kernel descriptor and the actual write SHALL change that thread's kernel name. | test_original_thread_name_write_changes_actual_kernel_comm |
| WHEN no broker is requested, THE snapshot SHALL preserve all existing creation/truncation and non-GPU write refusals. | test_thread_name_broker_default_preserves_write_refusals |
| WHEN a target is outside the original worker thread group or lacks original custody, THE broker SHALL refuse without a descriptor or rename. | test_thread_name_broker_refuses_foreign_or_unowned_task |
| WHEN path/flags/dirfd exceed the exact observed contract, THE broker SHALL refuse all other proc, device, model and host-file writes. | test_thread_name_broker_refuses_other_paths_flags_and_dirfds |
| WHEN the original target exits or its number is reused, THE broker SHALL refuse rather than act on the replacement. | test_thread_name_broker_refuses_dead_and_reused_target |
| WHEN pathname memory changes, THE broker SHALL decide from its bounded copied request and SHALL NOT continue the mutable original pathname syscall. | test_thread_name_broker_never_continues_mutable_path |
| WHEN a notification aborts or listener/control custody is lost, THE original controller SHALL preserve refusal, close only owned FDs and drain all original members within its bound. | test_thread_name_broker_aborted_request_and_controller_loss_drain |
| WHEN worker SDK code tries to remove isolation or acquire other authority, THE snapshot SHALL retain mandatory Landlock, readonly root/proc, zero capabilities and namespace/socket/FD restrictions. | test_thread_name_broker_preserves_actual_snapshot_isolation |
| WHEN a stronger original seccomp denial conflicts with broker notification, THE system SHALL refuse and SHALL NOT label notification installation alone as success. | test_thread_name_broker_refuses_conflicting_original_filter |
| WHEN the bounded actual driver or copied Torch test refuses, THE diagnostic SHALL retain the exact refusal and SHALL NOT report a CUDA/model/producer success from observer exit0. | test_thread_name_driver_refusal_is_not_gpu_admission |

## T1 Kernel Calibration Regressions

These named tests execute the approved mechanism on the real kernel before
production integration. They do not replace the production criteria above.

| Criterion | Named Regression |
| --- | --- |
| WHEN each isolated user-namespace/capability/Landlock calibration runs, THE probe SHALL independently measure the exact original thread rename after atomic descriptor injection. | test_thread_name_kernel_namespace_capabilities_and_landlock |
| WHEN the private root is exercised with and without a nested PID namespace, THE probe SHALL preserve read-only root/proc and zero controller/worker capabilities, observe the exact rename and remove private mounts on exit. | test_thread_name_kernel_private_root_changes_real_comm |
| WHEN a real foreign-path/extra-flags/wrong-dirfd/other-leaf/unterminated request reaches the listener, THE probe SHALL return kernel EPERM with no descriptor and unchanged target comm. | test_thread_name_kernel_refuses_unapproved_requests |
| WHEN real pathname bytes mutate after bounded copy, THE probe SHALL inject only the original anchored target descriptor without continuing the syscall. | test_thread_name_kernel_mutable_path_uses_copied_request |
| WHEN the original worker is killed through its original pidfd and exit is observed, THE kernel SHALL invalidate both ID_VALID and ADDFD_SEND for its old notification. | test_thread_name_kernel_stale_notification_refuses_after_original_drain |
| WHEN the last controller listener closes, THE actual worker open SHALL refuse with ENOSYS and leave the target comm unchanged. | test_thread_name_kernel_listener_loss_refuses_real_open |
| WHEN the original worker main thread names another live original thread through actual libc fopen(w), THE probe SHALL handle the captured0x241/0666 request, rename only the target and preserve the caller's name. | test_thread_name_kernel_vendor_main_names_its_other_live_thread |
