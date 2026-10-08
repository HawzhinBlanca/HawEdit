# EARS

1. WHEN Windows64 or required APIs are unavailable, THE native owner SHALL refuse
   without launching. test_native_owner_unsupported_platform_refuses.
2. WHEN launch paths, expected image hash, arguments, explicit environment or STD
   resources are invalid, THE owner SHALL refuse before executing child code.
   test_native_owner_rejects_invalid_launch_inputs;
   test_native_owner_wrong_image_hash_refuses;
   test_native_owner_refuses_invalid_stdio.
3. WHEN a child is created, THE owner SHALL retain its original creation handles,
   assign its private non-inherited job while suspended, verify actual image and
   membership, and resume only once. test_native_owner_never_runs_code_before_job_assignment;
   test_native_owner_runs_actual_child;
   test_native_owner_resume_is_single_use.
4. WHEN unrelated inheritable handles exist, THE owner SHALL inherit only explicit
   STD duplicates, not its job or unrelated handle.
   test_native_owner_stdio_handle_list.
5. WHEN the executable has been admitted, THE owner SHALL retain a read lease that
   refuses write/delete replacement until scope release.
   test_native_owner_holds_actual_image_lease.
6. WHEN the launcher exits but a native descendant remains, THE owner SHALL not
   report a successful quiescent result before the scope is empty.
   test_native_owner_launcher_exit_not_completion.
7. WHEN a deadline expires or stop is requested, THE owner SHALL terminate only
   its original owned job and verify root and observed-member signaling plus empty
   accounting/member list within bounded cleanup.
   test_native_owner_stop_terminates_actual_descendants[timeout];
   test_native_owner_stop_terminates_actual_descendants.
8. WHEN the owner dies abruptly, THE non-inherited last job handle SHALL close and
   stop original native members. test_native_owner_abrupt_parent_death.
9. WHEN ownership/shutdown becomes uncertain, THE owner SHALL refuse rather than
   return successful completion. Future integration SHALL retain durable attempt
   exclusion; test_native_owner_uncertain_shutdown_never_finishes_attempt is T3.
10. WHEN output exceeds limits, THE IO owner SHALL refuse and drain its exact
    scope. test_native_owner_output_limit_terminates_scope is T2, not implemented
    or claimed by T1.

This capability is neither a sandbox for malicious same-privilege code nor Linux,
billing, owner/model/security admission, delivery or publication authority.
Complete resource admission must retain every producer resource; unobserved
ephemeral native children are not certified terminated merely by empty accounting.
