# Native Member Transition EARS

- WHEN a bounded job list is transiently short, THE native owner SHALL obtain
  another actual query within a fixed eight-observation budget, never return the
  partial list or infer completion (test_native_owner_members_during_exit_transition).
- WHEN the original launcher exits while its actual descendant remains live, THE
  owner SHALL refuse completion and stop its owned scope at the requested deadline
  (test_native_owner_launcher_exit_not_completion and
  test_native_owner_members_during_exit_transition).
- WHEN owned termination finishes, THE owner SHALL observe all retained original
  handles signaled and a complete empty job list before releasing capabilities
  (test_native_owner_stop_terminates_actual_descendants).
- WHEN API/capacity or persistent enumeration uncertainty occurs, THE owner SHALL
  refuse rather than accept partial evidence or create another scope; existing
  cleanup-retention tests remain applicable, targeted real cases to be recorded.
  Actual API error coverage:
  test_native_owner_members_api_failure_never_becomes_empty.

New test names are planned until their actual executions are recorded. Unsupported
hosts exercise the existing refusal contract, not an asserted native execution pass.
