# EARS Specification

| Criterion | Requirement | Named Tests |
|---|---|---|
| AC1 | WHEN an inherited output writer remains beyond the deadline, THE audit capture SHALL refuse within the operation deadline plus bounded original cleanup, after both normal root exit and root timeout. | test_audit_deadline_covers_inherited_stream |
| AC2 | WHEN both output streams reach exact independent limits, THE capture SHALL preserve both complete streams and the return code, including16MiB stdout plus64KiB stderr. | test_audit_exact_independent_bounds, test_audit_full_scanner_output_contract |
| AC3 | WHEN either stream exceeds its own budget, THE capture SHALL refuse and identify that stream without unbounded buffering. | test_audit_one_byte_overflow |
| AC4 | WHEN true EOF occurs but the original root stays live, THE capture SHALL enforce the remaining deadline rather than report success. | test_audit_eof_does_not_complete_live_root |
| AC5 | WHEN malformed budgets/arguments are supplied, THE capture SHALL refuse before a marker-producing command can launch. | test_audit_invalid_budget_before_launch |
| AC6 | WHEN native independent limits are mixed/incomplete/invalid, THE native executor SHALL refuse before launch while preserving integer combined-budget behavior. | test_native_independent_limits_refuse_invalid_configuration; existing test_native_io_two_streams_share_one_limit and test_native_io_exact_combined_bound_passes |
| AC7 | WHEN POSIX capture refuses after execution or a WSL native capture fails, THE same owner SHALL retain uncertainty and refuse subsequent audit launches; no Linux/provider/effect completion is inferred. | test_audit_deadline_covers_inherited_stream; test_audit_one_byte_overflow |
| AC8 | WHEN normal control bytes/nonzero exit complete within budget, THE capture SHALL preserve exact binary stdout/stderr/code without claiming accepted evidence. | test_audit_binary_control_and_nonzero_exit |
| AC9 | WHEN a selected Windows image has multiple hard links, THE capture SHALL refuse actionably without copying or substituting an executable. | test_audit_linked_executable_refuses_actionably |

AC5 malformed commands additionally map to test_audit_invalid_command_refuses_before_launch.

Operation budget covers captured EOF and original-root completion. Existing
native cleanup/cancellation each has finite refusal/quarantine bounds; POSIX
original-root cleanup has five seconds. Tests measure actual generated faults,
not hardware-independent latency promises. Whole required caller coverage and
exact verify.sh remain required. No applicable same-SHA CI means WIP.
