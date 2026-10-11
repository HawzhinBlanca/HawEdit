# Private GPU EARS

Proposed requirements, no current pass claim. BLUEPRINT §§3,5,7,8.1-8.3;
D-325/D-326. Complete meaning/canonical ASR and existing acceptance thresholds
are unchanged. Kernel policy is not editorial quality or resource reservation.

| Criterion | Named Automated Regression |
| --- | --- |
| WHEN GPU opt-in is absent, THE snapshot SHALL preserve existing defaults and expose no GPU endpoint. | test_snapshot_default_excludes_private_wsl_gpu |
| WHEN mode, type, collision or mandatory kernel prerequisites are invalid, THE snapshot SHALL refuse before consumer release. | test_private_wsl_gpu_refuses_invalid_type, test_private_wsl_gpu_refuses_reserved_collision, test_private_wsl_gpu_requires_root_and_entropy, test_private_wsl_gpu_requires_enforced_policy_before_release |
| WHEN GPU acquisition occurs, THE snapshot SHALL bind only genuine original /dev/dxg10:258, with verified noninheritable O_PATH custody and no host-directory mount. | test_private_wsl_gpu_requires_original_character_description |
| WHEN an original is substituted or reopened, THE snapshot SHALL refuse and leave foreign descriptions open. | test_private_wsl_gpu_refuses_reopened_description_and_preserves_foreign_fd |
| WHEN the GPU policy is selected, THE snapshot SHALL enforce required leaf/namespace/network restrictions before SDK imports or any GPU I/O. | test_private_wsl_gpu_requires_enforced_policy_before_release |
| WHEN code reopens/writes entropy or regular files, THE GPU worker SHALL refuse through actual syscalls while retaining genuine entropy reads. | test_private_gpu_policy_preserves_entropy_and_file_write_refusal |
| WHEN code attempts async opens or namespace reentry, THE worker SHALL retain existing refusals. | test_private_gpu_policy_preserves_async_and_namespace_fence |
| WHEN code tries a new external socket or unapproved inherited description, THE worker SHALL refuse; offline flags alone SHALL NOT establish network isolation. | test_private_gpu_policy_refuses_external_network_and_foreign_handles |
| WHEN a child/thread/exec runs, THE enforced restrictions SHALL remain in effect without reopening outside authority. | test_private_gpu_policy_survives_fork_and_threads, test_private_gpu_policy_survives_exec |
| WHEN a private endpoint changes or policy installation fails, THE snapshot SHALL refuse and drain the original scope, not downgrade. | test_private_gpu_policy_refuses_endpoint_or_policy_drift |
| WHEN an explicitly authorized tiny CUDA consumer runs, THE diagnostic SHALL record actual device/tensor/synchronization results, hashes and limits, without asserting model/resource/producer admission. | test_private_gpu_consumer_retains_measured_config_and_admission_boundaries |

Portable hosts lacking required hardware must prove actionable refusal, never
skip or fabricate positive CUDA evidence. Actual positive endpoint/GPU evidence
must also exist on the target hardware before T2 model/adoption claims.

WHEN control descriptors are declared, THE snapshot SHALL refuse malformed,
missing, inheritable or kernel-nonblocking channels and incoming handle transfer.
Tests: test_private_wsl_gpu_refuses_invalid_control_declarations,
test_private_gpu_policy_refuses_unproven_control_channel,
test_private_gpu_policy_refuses_nonblocking_control_description,
test_private_gpu_policy_refuses_changed_control_flags,
test_private_gpu_policy_refuses_incoming_handle_transfer.
Outside abstract socket test: test_private_gpu_policy_refuses_outside_abstract_socket.
Tiny CUDA consumer criterion remains pending; copied Python or device-open
tests cannot satisfy tensor/model/resource/production admission.
