# EARS

Requirements are scoped composition checks, not release thresholds or readiness
claims. Every test below is initially planned, not pass evidence.

| ID | Requirement | Named test |
|---|---|---|
| HA1 | WHEN producer admission is requested, THE host SHALL use the installed studio profile, explicit named WSL runtime, current champion, six selected checkpoint verifications, shared device defaults and real fresh security gate. | test_host_admission_composes_selected_producers |
| HA2 | WHEN any runtime/model/security prerequisite refuses, THE host SHALL refuse before owner/transport consumption and preserve retained artifacts. | test_host_admission_preserves_prerequisite_refusal |
| HA3 | WHEN admission observations are repeated unchanged, THE deployment identity SHALL remain stable without binding the fresh audit timestamp or its own owner signature. | test_host_deployment_identity_is_stable |
| HA4 | WHEN source package, VEX or runtime identity changes during admission, THE host SHALL refuse the mixed observation. | test_host_admission_refuses_observed_drift |
| HA5 | WHEN signed route or confidentiality differs from selected producers, THE host SHALL refuse before billing storage or provider calls. | test_host_authorization_requires_exact_route_and_governance |
| HA6 | WHEN owner proof/trust changes, THE host SHALL reverify original raw proof and refuse; a constructed receipt SHALL NOT grant execution. | test_host_transport_reopens_owner_authority |
| HA7 | WHEN job execution binding is calculated, THE host SHALL bind deployment and raw owner document/signature/trust hashes without self-reference. | test_host_job_binding_includes_raw_proof |
| HA8 | WHEN a transport is prepared, THE host SHALL use the existing SignedStudioTransport and shared global billing journal, never an unguarded or per-job replacement pool. | test_host_transport_uses_signed_global_journal |
| HA9 | WHEN VEX bytes change during raw owner verification, THE host SHALL refuse the stale deployment observation. | test_host_refuses_vex_drift_during_owner_verification |
| HA10 | WHEN configured raw trust changes during transport construction, THE host SHALL refuse the mixed binding before a provider call. | test_host_refuses_trust_drift_during_transport_construction |
| HA11 | WHEN distinct jobs use one signed owner pool, THE transport factory SHALL retain the global reservation ceiling across both jobs. | test_host_transports_share_owner_budget_across_jobs |
