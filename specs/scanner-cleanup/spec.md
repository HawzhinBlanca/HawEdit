# EARS Specification

- SC1: WHEN scanner storage is created, THE launcher SHALL capture a strict
  identity before writing requirements. Tests: test_scanner_storage_create_and_cleanup,
  test_scanner_directory_identity_rejects_invalid_receipts.
- SC2: WHEN storage identity/path/ownership is unsafe or changed, THE cleanup
  SHALL refuse without deleting the replacement or symlink target. Tests:
  test_scanner_storage_refuses_changed_identity,
  test_scanner_storage_refuses_symlink_root,
  test_scanner_storage_unlinks_child_symlink_without_following.
- SC3: WHEN requirements materialization or scanner execution fails, THE launcher
  SHALL attempt owned cleanup and retain the original failure. Tests:
  test_scanner_write_failure_still_cleans_owned_directory,
  test_scanner_cleanup_failure_preserves_original_error.
- SC4: WHEN cleanup fails after a successful audit, THE launcher SHALL refuse
  accepted evidence. Test: test_scanner_cleanup_failure_refuses_success.
- SC5: WHEN storage operations run on an unsupported platform, THE helper SHALL
  refuse before filesystem mutation. Test: test_scanner_storage_create_and_cleanup.
- SC6: WHEN cleanup exceeds its recursion budget, THE helper SHALL refuse and
  retain the remaining tree. Test: test_scanner_storage_bounds_recursive_work.

Filesystem tests execute real code, not mocked deletion. No VEX acceptance,
performance, release or human-review claim follows from these tests.
