# Sidecar EARS

| Criterion | Regression |
| --- | --- |
| WHEN sidecar validation raises but the inspected path has genuinely disappeared, THE private journal SHALL preserve its existing absence contract and recheck original root/main binding. | test_studio_private_disappearing_invalid_sidecar_is_absent_not_adopted |
| WHEN an invalid sidecar remains or is replaced during inspection, THE private journal SHALL refuse rather than adopt the new path. | test_studio_private_changed_invalid_sidecar_is_not_adopted; test_studio_private_linked_sidecars_refused |
| WHEN jobs compete for one authorized pool, THE billing transport SHALL atomically refuse oversubscription without weakening journal/private-storage validation. | test_studio_billing_concurrent_jobs_cannot_oversubscribe_pool |

These are local storage/billing controls, not real cloud-spend or ZAR output claims.
