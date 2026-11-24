# Attempt Journal EARS

| ID | Requirement | Named test |
|---|---|---|
| AJ1 | WHEN initial execution is reserved, THE journal SHALL bind it to an existing immutable submission and a bounded run ID, with a private distinct SQLite path and running state. | test_attempt_binds_real_submission_and_preserves_outbox |
| AJ2 | WHEN duplicate or concurrent execution is requested, THE journal SHALL refuse without adding work or overwriting retained evidence. | test_attempt_duplicate_and_serial_launch_refuse |
| AJ3 | WHEN a process exits or storage is reopened, THE journal SHALL retain committed events and running uncertainty, refusing automatic relaunch. | test_attempt_process_exit_retains_uncertainty |
| AJ4 | WHEN a producer emits an event, THE journal SHALL atomically append only the next contiguous sequence for the bound run, with strict finite/type/byte limits. | test_attempt_events_are_transactional_and_scoped,test_attempt_rejects_malformed_event |
| AJ5 | WHEN retained evidence is read, THE journal SHALL refuse malformed schema, types, strings, mismatched source/config/binding, foreign objects and altered event identities without omission or repair. | test_attempt_refuses_corrupted_evidence,test_attempt_refuses_foreign_schema |
| AJ6 | WHEN a terminal private outcome is recorded, THE journal SHALL preserve events, refuse later mutation and never represent verified publication or completed delivery. | test_attempt_terminal_outcome_is_not_publication |
| AJ7 | WHEN storage contention or namespace loss occurs, THE journal SHALL surface a bounded failure and SHALL NOT report an outcome that was not committed. | test_attempt_storage_contention_is_bounded,test_attempt_refuses_replaced_storage |

SQLite synchronous FULL is the requested commit policy, not a universal hardware
power-loss guarantee. Test results must carry host/runtime/SHA. No retry, billing
settlement, WSL child quiescence, render/quality or publication proof is claimed.
