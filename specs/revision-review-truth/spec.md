# EARS Requirements

| ID | Requirement | Named Regression |
| --- | --- | --- |
| RT1 | WHEN a pending caption revision has occupied artifacts or retained render claim, THE proposal SHALL refuse with reconciliation context without changing any bytes. | test_caption_revision_proposal_refuses_reconciliation_without_writing |
| RT2 | WHEN a pending boundary revision has occupied artifacts or retained render claim, THE proposal SHALL refuse with reconciliation context without changing any bytes. | test_boundary_revision_proposal_refuses_reconciliation_without_writing |
| RT3 | WHEN a private caption revision renders, THE record SHALL derive prior_qc_invalidated from original QC and require fresh review without auto/human approval. | test_caption_revision_invalidation_records_original_review_state |
| RT4 | WHEN a private boundary revision renders, THE record SHALL derive prior_qc_invalidated from original QC and require fresh review without auto/human approval. | test_boundary_revision_invalidation_records_original_review_state |

Original review marker is not signature verification. Revised MP4/sidecars remain
private; detached trust/hash-bound approval and reconciliation are still required
before publication. Old canonical transcript/anchors and original report bytes
stay unchanged. D-321 atomic refusal remains authoritative after a proposal race.
