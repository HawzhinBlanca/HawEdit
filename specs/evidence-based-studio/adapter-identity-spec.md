# Adapter Identity EARS

Approved scope: parent T3 model identity prerequisite, not a new model/runtime policy.

| ID | Requirement | Named regression |
|---|---|---|
| AI1 | WHEN tokenizer bytes change while config/weights do not, THE identity SHALL change for both native and WSL producers. | test_tokenizer_change_changes_both_adapter_identities |
| AI2 | WHEN an identity is computed, THE identity SHALL bind separated roles/names/sizes/hashes for all three stable files and retain full SHA256. | test_adapter_identity_is_full_versioned_three_file_digest |
| AI3 | WHEN required files are missing, ambiguous, linked, nonregular or change during reading, THE identity SHALL refuse without rewriting input. | test_adapter_identity_refuses_unsafe_or_ambiguous_inputs, test_adapter_identity_refuses_drift_between_descriptor_checks |
| AI4 | WHEN a bridge request claims missing/foreign/malformed adapted identity, THE worker SHALL refuse before model inference or output creation. | test_worker_refuses_foreign_adapter_identity_before_inference |
| AI5 | WHEN a worker returns a different adapter or the host bundle changes during the request, THE host SHALL refuse that result. | test_host_refuses_foreign_worker_adapter_provenance, test_host_refuses_tokenizer_drift_during_worker |
| AI6 | WHEN a native inference or cached backend's bundle identity changes, THE producer SHALL refuse rather than relabel old loaded models or publish changed-input transcripts. | test_cached_backend_refuses_changed_adapter_identity, test_producer_refuses_identity_drift_during_inference |
| AI7 | WHEN no adapter is selected, THE native/WSL path SHALL preserve stock identity/schema and existing canonical alignment/validator behavior. | test_a_stock_wsl_request_contains_only_the_required_schema_fields |
| AI8 | WHEN a changed adapter conflicts with a persisted request, THE bridge SHALL preserve the prior request/output and give non-destructive recovery guidance. | test_changed_adapter_resume_preserves_prior_request_and_output |

- [ ] AI1-AI8: exact canonical gate and same-SHA required CI, plus applicable caller tests.

Filesystem/protocol tests are not canonical inference, throughput, held-load security or
licence acceptance. Preserve all original ASR/media and keep the full release thresholds.
