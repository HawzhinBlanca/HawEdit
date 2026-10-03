# Bounded Intake EARS

Extends parent T3, BLUEPRINT sections2-5 and D-276; does not certify execution authority.

| ID | Requirement | Named regression |
|---|---|---|
| BI1 | WHEN pending records exceed the row budget, THE store SHALL refuse before decoding any record and preserve all original work. | test_pending_overflow_refuses_before_decode_and_preserves_jobs |
| BI2 | WHEN aggregate persisted text exceeds the byte budget, THE store SHALL refuse before decoding rather than return a truncated batch. | test_pending_byte_overflow_refuses_before_decode |
| BI3 | WHEN limits are malformed or outside reviewed local bounds, THE store SHALL refuse them before querying. | test_invalid_intake_limits_are_refused |
| BI4 | WHEN SQLite VM progress exceeds its deadline, THE store SHALL report a query-budget refusal and preserve the ledger. | test_native_query_deadline_refuses_without_losing_jobs |
| BI5 | WHEN exact recovery IDs exist, THE store SHALL return their validated immutable records in requested order including confirmed dispatch. | test_recovery_snapshot_reads_exact_ids_in_requested_order |
| BI6 | WHEN recovery IDs are duplicate, missing, malformed or over budget, THE store SHALL refuse without dropping an ID. | test_recovery_snapshot_never_omits_or_duplicates_work |
| BI7 | WHEN selected identifiers/state/timestamps are oversized or wrong-typed, THE store SHALL retain contextual invalid-record refusal, not validate a truncated value. | test_bounded_projection_does_not_repair_invalid_records |
| BI8 | WHEN normal pending and lookup callers read valid private state, THE store SHALL preserve their existing immutable identity/token/acknowledgement behavior. | test_normal_pending_snapshot_preserves_list_contract; existing complete submission/storage/queue/generation tests |
| BI9 | WHEN damaged state has a null SQLite text primary key, THE store SHALL refuse contextually without repairing or erasing it. | test_null_primary_key_refuses_contextually_without_repair |
| BI10 | WHEN byte intake exceeds its budget, THE reader SHALL refuse while incrementally collecting rows, not bulk materialize the remaining batch first. | test_byte_refusal_does_not_bulk_materialize_remaining_records |

Budgets apply to returned record count and encoded persisted text, not Python object/RSS
or whole SQLite native I/O. Progress callbacks bound observed VM work/deadline checks, not
an absolute wall-clock deadline while native I/O is blocked. No generation/publication claim.
