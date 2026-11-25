# EARS

- WHEN native IO starts, THE executor SHALL independently inspect private pipe
  ACLs and own client identity before child execution.
  Test: test_native_io_acl_policy_reads_actual_descriptor.
- WHEN IO remains pending, THE executor SHALL retain original memory, event and
  handle until actual completion, not cancellation request alone.
  Test: test_native_io_pending_cancel_keeps_original_memory_until_completion.
- WHEN input/output overlap, THE executor SHALL service bounded chunks fairly.
  Tests: test_native_io_binary_input_and_independent_streams;
  test_native_io_output_flood_refuses_while_input_blocked.
- WHEN combined output exceeds its bound, THE executor SHALL refuse and stop its
  held original scope. Tests: test_native_io_output_overflow_refuses_original_scope;
  test_native_io_two_streams_share_one_limit; test_native_io_exact_combined_bound_passes.
- WHEN a deadline expires, THE executor SHALL refuse; EOF SHALL NOT finish a live
  root/member. Tests: test_native_io_nonreader_deadline_drains_pending_input;
  test_native_io_true_eof_does_not_complete_live_original;
  test_native_io_root_exit_does_not_complete_live_native_writer.
- WHEN constraints are invalid, THE executor SHALL refuse before launch.
  Tests: test_native_io_invalid_deadline_refuses_before_launch;
  test_native_io_invalid_output_bound_refuses_before_launch;
  test_native_io_nonimmutable_input_refuses_before_launch;
  test_native_io_oversized_input_refuses_before_launch.
- WHEN a child closes input prematurely, THE executor SHALL refuse incomplete
  delivery. Test: test_native_io_closed_child_input_is_refusal.
- WHEN native bytes return, THE executor SHALL NOT claim pipeline/admission/
  review/billing/publication completion.
  Test: test_native_io_empty_output_and_nonzero_exit_are_not_completion.
- WHEN another native execution is already active, THE executor SHALL refuse
  without waiting or allocating another scope.
  Test: test_native_io_concurrent_scope_refuses_without_waiting_for_active_worker.
- WHEN cleanup cannot verify the original resource, THE executor SHALL retain
  memory and refuse future launches in that process.
  Test: test_native_io_uncertain_original_handle_retains_memory_and_refuses_launch.
- WHEN an owner dies with IO pending, THE tests SHALL independently observe
  original owned descendant signaling without treating OS teardown as billing
  or publication completion.
  Test: test_native_io_pending_reads_owner_death_signals_original_native_member.
- WHEN a cancellation request succeeds, THE executor SHALL NOT release pending
  memory until actual completion is observed.
  Test: test_native_io_actual_cancel_request_does_not_release_pending_memory.
