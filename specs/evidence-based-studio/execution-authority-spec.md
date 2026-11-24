# Execution Authority EARS

Extends approved plan/D-276, BLUEPRINT §3 governance and §7 provider identity.
Acceptance remains exact canonical gate plus applicable same-SHA CI; all rows pending.

| ID | Criterion | Named regression |
|---|---|---|
| EA1 | WHEN trusted raw execution proof binds current producer/context and bounded policy, THE loader SHALL report its exact signed digest and derived reservation policy without claiming runtime readiness. | test_signed_studio_authorization_binds_real_proof_and_policy |
| EA2 | WHEN proof, owner principal, purpose, schema, source/context or time is invalid, THE loader SHALL refuse before storage adoption or upstream requests. | test_signed_studio_authorization_refuses_invalid_signed_document; test_signed_studio_authorization_refuses_wrong_key_or_namespace |
| EA3 | WHEN authority/document/proof changes or disappears, THE transport SHALL refuse cached replay and all new upstream calls. | test_signed_studio_transport_reopens_authority_for_replay; test_signed_studio_transport_refuses_changed_raw_proof |
| EA4 | WHEN trust is revoked during token counting, THE transport SHALL send no generation or billed intent. | test_signed_studio_transport_rechecks_after_count |
| EA5 | WHEN generation may have happened but trust/response confirmation fails, THE journal SHALL retain its positive uncertain reservation and SHALL refuse blind replay. | test_signed_studio_transport_retains_uncertainty_after_revocation |
| EA6 | WHEN confirmed response evidence is replayed under unchanged current raw authority, THE transport SHALL reuse its actual committed response without another count/generation. | test_signed_studio_transport_replays_under_current_raw_authority |
| EA7 | WHEN multiple jobs share the same signed authorization, THE journal SHALL enforce the existing single reservation pool and refuse excess generation. | test_signed_studio_transport_shares_signed_reservation_pool |
| EA8 | WHEN configured private authority storage is unsafe, missing or changed, THE loader SHALL refuse without repairing original permissions or bytes. | test_signed_studio_authorization_refuses_unsafe_storage |

- [ ] EA1-EA8: protocol implementation evidence pending; no accepted row.
