# Signed Delivery Caller Impact

## SD-A Implementation Map (2026-10-03)

New candidate_review.py initially has no engine callers. Before its first fixes, actual
Serena definition/reference queries mapped _stamp, _snapshot, _record, _bindings,
prepare_candidate_review and verify_candidate_review plus the strict-claims regression.
Raw records: SD-A-before-fix-serena.json; log: SD-A-before-fix-serena.log (7 records).
_stamp feeds _snapshot; _snapshot feeds bounded reads, bindings, preparation and verification.
_record and _bindings feed both public APIs. Public APIs are called only by ReviewCase
prepare/verify in test_candidate_review.py. No delivery/pipeline/export route is wired yet.
Tests cover both APIs, all seven frozen members, proof/context/trust tampering and raw claims.
The native first run preserved 30 failures/10 passes, including the actual Windows path/fd
ctime mismatch; fixes retain within-view ctime and cross-view identity/mtime/size/link checks.

Before the native-armor fix, all 41 top-level new module/test definitions were individually
resolved with actual Serena and their referencing symbols queried. Raw JSON/log:
SD-A-before-native-proof-fix-serena.json/.log. _signature is called by
verify_candidate_review; changed pytest functions have no source callers. Both API routes
remain test-only. Negative packet/context/trust/schema tests now verify the intact packet
successfully before altering it, preventing a blanket refusal from masquerading as coverage.

Token-budget follow-up: the same actual _configuration definition/references in the 41-record
map were reopened before editing its unchanged guard. Callers are only preparation and
verification. Existing studio_billing.BillingPolicy has max_input_tokens/max_output_tokens;
substring "token" cannot classify those limits or tokenizer_revision as credentials. New
configuration regressions cover legitimate bindings and named credential refusal, in addition
to the original nested credential/depth/nonfinite tests. The first full gate was explicitly
stopped after discovering this bug, not graded as a pass; its partial log and exit127 are
retained outside the checkout under studio-commit-98dc257... with gate-interruption.md.

Documentation callers: existing tests.test_claims.test_the_module_map_covers_every_module
and test_the_ledger_accounts_for_every_module compare all runtime files to README/PROGRESS
table rows. Reproduced 2 failures/65 passes before adding the new module's README map and
M9.48 WIP entry. No existing row status, test or assertion is modified. The second partial
canonical run is also explicitly preserved as incomplete exit127 under studio-commit-6555d1f...
with its frozen manifest, original partial log and gate-interruption.md. Complete gate evidence
must be captured on the later clean documentation checkpoint, not inferred from either run.

Actual 22-record Serena map at 85b01f101a3bd81922fb53b3c8a8999b88c74a2e. Every row below
is grounded in definitions/references, not a guessed API. New proposed APIs have no callers
yet. Revalidate definitions/references immediately before later edits if source changes.

| Existing symbol | Actual caller surface | Required coverage |
|---|---|---|
| QcRecord and Qc.from_record | clip, comparison_kit, delivery, pipeline; clip/delivery/judge-calibration/pipeline/prompt-injection tests | Preserve metadata parsing; refuse metadata as authority; keep comparison-to-QC refusal |
| Clip.assert_renderable | delivery, pipeline, render; agent/audit/clip/judge-calibration/story tests | Separate renderability from publication authorization; no mutable flags become approval |
| promote_candidate | pipeline, delivery export list, delivery tests | Exact signed bytes, fresh real measurements, source/config identity, wrong/missing trust and altered/stale evidence |
| reconcile_delivery | delivery, pipeline; cover/delivery tests | Preserve measured policy refusals; cached valid-shaped measurements cannot bypass fresh checks |
| publish_delivery_bundle | delivery and cover/timeline tests | Generic packaging is not authenticated publication; classify and protect any delivery use |
| run_pipeline | pipeline, legacy web; checkpoint/episode/events/pipeline/render-revision/review/cost/screener tests | No unsigned direct or promotion route; review-only default and truthful stages/recovery |
| _render_episode_single_clip / _run_episode_delivery | pipeline | Episode-level public bundles require the same authorization, not self-declared Qc |
| build_parser / _build_and_run | pipeline/durable/durable_workflow/episode/studio_generation; broadcast/content/durable/episode/pipeline/pro-repurpose/studio billing/generation tests | Shared producer parity; plain --qc-record remains unverified metadata; policy cannot come from web request |
| measure_clip / probe_container | measure, pipeline, render; measure/pipeline/robustness/media/studio/web tests | Actual media decode/measurement, source/tool identity, bounded failures; no model/provider calls in authentication tests |
| ArtifactBundle / ArtifactBundle.publish | artifact_bundle/delivery/pipeline; bundle/pipeline/robustness/workflow-recovery tests | Keep atomic no-overwrite seven-file legacy packaging; version exact proof-bearing publication set and rejection of unexpected members |
| release/editorial _verify_signature and release bound readers/canonical serializer | respective modules only | Keep their namespaces, raw signature verification, snapshot/duplicate-key protections and existing integration tests |

Static source inspection also finds direct pipeline bundle publication at the episode
render path and the single-clip render path. The fresh map records 19 ArtifactBundle.publish
references; enumerate concrete publication contexts before integration rather than changing
generic packaging into approval. Rendering private candidates and packaging diagnostic or
timeline files must remain possible without falsely reporting a completed deliverable.

All tests named in signed-delivery-spec.md are planned, not asserted to exist or pass.
Existing covered assertions must remain meaningful. Replace false-authority expectations
with stronger refusal checks, never disable a test or relax policy for easier fixtures.
