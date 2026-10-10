# Rooted Kernel Entropy EARS

Tests are obligations; local kernel evidence is not full-gate/CI acceptance.

| ID | Requirement | Named Regression |
| --- | --- | --- |
| E1 | WHEN entropy is not requested, THE snapshot SHALL preserve existing defaults and expose no private entropy endpoint. | test_rooted_entropy_default_is_absent |
| E2 | WHEN explicit rooted entropy is requested, THE snapshot SHALL admit only the genuine original readonly urandom endpoint with verified character identity and descriptor custody. | test_rooted_entropy_original_readonly_endpoint |
| E3 | WHEN a data-only or untyped entropy option is supplied, THE snapshot SHALL refuse before transition. | test_rooted_entropy_mode_and_type_refusals, test_rooted_entropy_data_only_refuses |
| E4 | WHEN a declaration collides with the reserved entropy path, THE snapshot SHALL refuse before copying/mounting. | test_rooted_entropy_declaration_collision_refuses |
| E5 | WHEN an endpoint or original description changes, THE snapshot SHALL refuse and SHALL NOT close a foreign substituted description. | test_rooted_entropy_substitution_and_cleanup_refuse |
| E6 | WHEN the native endpoint mount/read-only policy cannot be established, THE snapshot SHALL refuse without exposing a host directory or relaxing its fence. | test_rooted_entropy_kernel_mount_refusal |
| E7 | WHEN the retained copied Python is re-executed with admitted entropy, THE consumer SHALL initialize using genuine kernel entropy and consume only the private original configuration despite outside replacement. | test_rooted_entropy_actual_copied_python_consumer |
| E8 | WHEN opt-in entropy is exposed, THE snapshot SHALL refuse writable/creating/truncating open, openat and creat calls and uninspectable openat2 calls, while preserving readonly reads and default fences. | test_rooted_entropy_writable_syscalls_refuse |
| E9 | WHEN a caller retains a writable entropy description, THE rooted initializer SHALL refuse rather than claim an unwritable endpoint. | test_rooted_entropy_preexisting_writer_refuses |
| E10 | WHEN explicit readonly entropy is admitted, THE snapshot SHALL refuse asynchronous io_uring entry points and retained ring handles rather than permit alternate writable-open routes. | test_rooted_entropy_async_open_syscalls_refuse, test_rooted_entropy_preexisting_ring_refuses |

Every success still requires actual kernel/byte/custody proof, not boolean
assertions presented as production admission. D-325/defaults and #24 stand.
