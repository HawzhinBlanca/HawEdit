# EARS

| ID | Criterion | Regression |
| --- | --- | --- |
| LS1 | WHEN actual supported dedicated namespace initialization admits declared bytes, THE snapshot SHALL expose only an owned readonly copy matching declared hashes/sizes. | test_linux_snapshot_copies_actual_media_and_refuses_mutation |
| LS2 | WHEN mutable source backing changes after preparation, THE snapshot SHALL retain exact original copied bytes. | test_linux_snapshot_survives_source_backing_mutation |
| LS3 | WHEN source bytes/names/files or finite resource budgets are invalid, THE snapshot SHALL refuse before producer release and leave source bytes unchanged. | test_linux_snapshot_source_refusals; test_linux_snapshot_invalid_declarations; test_linux_snapshot_invalid_bounds |
| LS4 | WHEN descendant attempts namespace reentry/remount/ABI bypass, THE snapshot SHALL refuse that mutation while permitting ordinary tested fork/thread behavior. | test_linux_snapshot_fence_and_inheritance |
| LS5 | WHEN the original owner/namespace/root descriptor is foreign, closed or replaced, THE live snapshot SHALL refuse use rather than accept a replayed description. | test_linux_snapshot_original_owner_and_descriptor_refusal |
| LS6 | WHEN host or caller lacks the mandatory kernel/platform/initial namespace state, THE snapshot SHALL refuse without filesystem mutation. | test_linux_snapshot_unsupported_host_or_caller |

Actual kernel checks are required. Test metadata/signature/hash assertions do not establish editorial quality, complete producer admission, total memory/GPU bound or authenticated approval.

Additional named LS3--LS5 controls: test_linux_snapshot_capacity_and_path_refusals,
test_linux_snapshot_complete_tree_and_kernel_write_refusals,
test_linux_snapshot_namespace_clone_and_exec_fence,
test_linux_snapshot_root_rename_keeps_original_bytes, and
test_linux_snapshot_same_inode_foreign_description_cleanup. Descriptor cleanup
must never close a same-inode foreign reopened description. Uncertain original
descriptors are left for mandatory original process-scope drain, not fabricated
as fully released by close().
