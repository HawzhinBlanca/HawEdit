# Community-1 Impact

The planned edit is one protected metadata row, not source implementation.
Consumers: ModelStore.integrity/assert_checkpoint_provisionable/verify_checkpoint;
build_fetch_plan/fetch_checkpoint and readiness; diarization provisioning;
environment/model asset digests and independent VEX. Run existing model-fetch,
model-store, registry, environment, diarization and claims regressions and the
canonical gate. Preserve actual gated metadata/invalid-hash refusal cases.

The legacy negative test currently reads the checked-in blocked row. Preserve
its strict assertion using the same historical blocked data in a real temporary
metadata root, and separately cover newly measured verified metadata. Existing
test_tracked_integrity_manifest_covers_every_weight_repository already validates
either blocked or verified schemas. Map both actual test definitions/references
and the model-store consumers with Serena before edits under the approved plan.

No production source edits are proposed or performed; the approved plan includes
only the strict test-input transition above. Any additional production source
change requires actual Serena symbol/reference mapping, caller coverage and a
separate approved extension before implementation. Existing fetcher cannot be bypassed
by an ad hoc external manifest, SDK environment override or guessed digest.

Actual Serena 2026-10-14: seven definition/reference pairs at 5a5b284, unchanged
source before/after, C:/Users/Wareen/HawEditCommunity1Map-5a5b284-20261014/serena-map.json.
Integrity callers: provisionability, verification and model tests. Verification
callers: fetch stages/final path, readiness, ASR journal, checkpoint access and
studio deployment capture. Fetch-plan callers: CLI and planning tests; fetch
callers: CLI and model-fetch tests. Both changed test definitions have no static
callers. Cover models, model_fetch, registry, environment, diarization, ASR resume,
studio host and evidence claims, then the complete canonical gate.
