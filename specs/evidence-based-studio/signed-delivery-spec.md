# Signed Delivery EARS

Proposed extension of BLUEPRINT §§2-5, D-263/D-274/D-276 and the approved parent review/
artifact/completion contracts. These test names are planned regressions, not current passes.

| ID | Requirement | Planned named test |
|---|---|---|
| SD1 | WHEN a plain QcRecord or human_reviewed flag is presented, THE publication engine SHALL treat it as metadata and refuse authorization without trusted detached proof. | test_plain_qc_cannot_authorize_any_publication_route |
| SD2 | WHEN a trusted reviewer signs the canonical review envelope for a real decoded candidate, THE engine SHALL verify principal, dedicated namespace and exact envelope bytes before accepting approval. | test_real_openssh_review_approves_bound_decoded_candidate |
| SD3 | WHEN any MP4, sidecar, final editing JSON, edit plan, source, effective configuration or producer identity differs from the reviewed binding, THE engine SHALL refuse publication. | test_changed_review_binding_refuses_publication |
| SD4 | WHEN measurement JSON describes invalid or damaged media, THE engine SHALL refuse publication after fresh inspection of the same bound bytes, regardless of valid-shaped cached values. | test_forged_measurement_cannot_publish_invalid_media |
| SD5 | WHEN public delivery succeeds, THE engine SHALL copy the exact frozen reviewed bytes and proof set atomically without mutating the approved JSON or rerendering the MP4. | test_signed_publication_preserves_every_reviewed_byte |
| SD6 | WHEN a signature, trust policy, identity, namespace, timestamp or record is absent, malformed, changed, stale or unauthorized, THE engine SHALL refuse with an actionable reason. | test_invalid_review_authority_refuses_publication |
| SD7 | WHEN rendering is requested without authenticated approval, THE pipeline SHALL produce only a private review candidate and SHALL NOT report a completed publication. | test_unsigned_single_clip_and_episode_remain_private |
| SD8 | WHEN a publication is retried, interrupted or concurrently submitted, THE engine SHALL preserve the no-overwrite/recovery contract and SHALL NOT duplicate or overwrite publication. | test_signed_publication_retry_and_recovery_are_bound |
| SD9 | WHEN legacy QC/clip records are loaded, THE system SHALL preserve their original bytes and SHALL NOT infer authenticated approval from their metadata. | test_legacy_review_metadata_stays_unverified |
| SD10 | WHEN approved artifacts are exported or consumed later, THE engine SHALL reverify raw proof and configured trust against current bound artifacts rather than trust a mutable result object or True flag. | test_export_reopens_signed_review_evidence |

The cryptographic mechanics tests use ephemeral test keys and real decoded synthetic media
with explicit provenance, not commissioned editor or native-speaker sign-off. Every final
product publication must also satisfy the frozen production reconciliation and human review
requirements. No fixture profile, fake duration/score or relaxed policy may make a production
acceptance claim. Speaker identity and semantic quality remain separate labelled/human gates.

2026-10-03 SD-A observation: 58 actual verifier/preparation mechanics cases now exist in
test_candidate_review.py. SD2/SD3/SD6/SD9 names there cover this authentication boundary only.
They do not exercise or repair existing public delivery paths. Those end-to-end EARS
publication obligations remain pending SD-B/SD-C, canonical gate and same-SHA CI.
