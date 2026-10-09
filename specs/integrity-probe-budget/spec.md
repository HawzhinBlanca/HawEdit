# EARS

| ID | Requirement | Named Test |
|---|---|---|
| B1 | WHEN an integrity budget is invalid, THE probe SHALL refuse before receipt/filesystem/child work; accepted budgets are integers1..1800 excluding bool. | test_integrity_probe_invalid_budget_refuses_before_receipt |
| B2 | WHEN the probe uses its default budget, THE system SHALL use bounded300seconds and retain the complete live card/asset integrity command. | test_integrity_probe_default_budget_is_bounded_and_keeps_all_hashes |
| B3 | WHEN a valid explicit budget is selected, THE probe SHALL pass that exact budget to the unchanged complete integrity command. | test_integrity_probe_selected_budget_retains_full_hash_command |
| B4 | WHEN the process times out or cannot start, THE probe SHALL report actionable WslRuntimeError with original cause and no verified-readiness claim. | test_integrity_probe_process_failure_is_actionable_refusal |
| B5 | WHEN the output is malformed or file/byte/device observations drift, THE probe SHALL retain existing fail-closed refusals even with a larger budget. | test_integrity_probe_malformed_output_still_refuses_with_larger_budget,test_integrity_probe_drift_still_refuses_with_larger_budget |
| B6 | WHEN the live gate selects a valid budget, THE system SHALL forward it to final full integrity verification; a refusal SHALL publish no accepted evidence. | test_live_gate_forwards_selected_budget_to_final_integrity_probe |
| B7 | WHEN a live-gate budget is invalid, THE system SHALL refuse before receipt/filesystem/child work without publishing evidence. | test_live_gate_invalid_budget_refuses_before_receipt |

300seconds is an operational default, not a cross-hardware completion or
performance guarantee. Current advisories, qualified VEX, original Linux/GPU/
provider cleanup, model terms, authentic review/CI/release evidence remain
independent. No policy weakening or BLUEPRINT/model/routing divergence.
