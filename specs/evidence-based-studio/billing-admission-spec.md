# Billing Admission EARS

Every row is proposed until its named test executes. No claim of paid-provider or release
acceptance follows from local synthetic protocol tests.

| ID | Criterion | Named Test |
| --- | --- | --- |
| BA1 | WHEN complete stored policy has a hidden suffix, THE transport SHALL preserve/refuse before either route or adoption. | test_studio_billing_policy_projection_suffix_refused |
| BA2 | WHEN intent keys or state conceal bytes, THE transport SHALL refuse before another request. | test_studio_billing_hidden_intent_cannot_escape_admission |
| BA3 | WHEN complete response binding changes, THE transport SHALL refuse replay without egress. | test_studio_billing_response_projection_suffix_refused |
| BA4 | WHEN schema/types/UTF-8/keys/field bounds are unsupported, THE transport SHALL preserve/refuse admission. | test_studio_billing_native_admission_refuses_foreign_storage |
| BA5 | WHEN corruption exists outside the current job/pool filter, THE transport SHALL refuse count/generate/replay. | test_studio_billing_admission_audits_foreign_pool_rows |
| BA6 | WHEN native evidence changes during count, THE transport SHALL refuse generation. | test_studio_billing_journal_drift_during_count_prevents_generation |
| BA7 | WHEN an existing guard's journal changes, THE transport SHALL refuse direct count before egress. | test_studio_billing_direct_count_refuses_invalid_journal |
| BA8 | WHEN evidence/persistence changes after generation, THE transport SHALL retain uncertain intent and refuse retry. | test_studio_billing_confirmation_drift_stays_uncertain; test_studio_billing_storage_failures_are_atomic |
| BA9 | WHEN valid jobs/pools share a journal, THE transport SHALL preserve policy-specific reservation/replay/occurrence behavior. | test_studio_billing_valid_multiple_pools_remain_usable; existing billing tests |
| BA10 | WHEN complete admission exceeds row/byte/deadline limits, THE transport SHALL refuse without omitting or removing records. | test_studio_billing_whole_journal_limits_preserve_evidence |
