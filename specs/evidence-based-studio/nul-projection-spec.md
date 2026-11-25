# Exact Projection EARS

NP1: WHEN a bounded raw projection differs from original encoded bytes, THE inspector SHALL
refuse before JSON or tag interpretation. Test: test_raw_nul_prefix_refuses_without_repair.
NP2: WHEN an outbox snapshot/state/diagnostic/ID has a hidden NUL suffix, THE store SHALL
refuse across get/pending/recovery without repair. Tests: test_outbox_nul_prefix_refuses,
test_outbox_hidden_job_id_refuses.
NP3: WHEN a caller supplies a NUL diagnostic, THE store SHALL refuse before writing it.
Test: test_outbox_nul_diagnostic_is_not_written.

All prior Unicode, size, native deadline, malformed-record and genuine DBOS controls remain.
No task is accepted until exact clean gate and applicable same-SHA CI; no broader safety claim.
