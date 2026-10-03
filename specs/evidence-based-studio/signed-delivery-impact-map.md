# Signed Delivery Caller Impact

## SD-B Consumption Map (2026-10-03)

Fresh actual Serena definitions/references are captured sequentially in
SD-B-before-map.json and SD-B-before-serena.log before existing source edits. Promotion
has the pipeline and two delivery-test callers. Direct single-clip and episode renders
must remain private even when legacy Qc says human_reviewed. Remove the fabricated date/
watched-seconds promotion reconstruction; host-selected raw proof is the only promotion
input. Generic seven-member packaging remains available for private/diagnostic bundles.
The approved fixed proof-bearing variant adds only review.json and review.sig, with
private staging and existing atomic no-overwrite semantics. Existing bundle methods and
their delivery/pipeline/recovery callers are mapped before editing them.

New candidate_publication APIs will consume raw proof, not a verified receipt; freeze the
configuration, require the current producer package and actual FFmpeg/ffprobe hashes,
decode/measure the exact private staged media within bounded subprocesses, validate the
source/output clock and edit-plan-derived sidecars, reconcile with production policy, and
reopen proof/context at consumption. Cached measurements are never authority; compare
their claims to fresh observations without altering the reviewed measurement sidecar.
Labelled speaker identity remains unavailable: speaker_face publication must refuse rather
than infer identity from a face or turn label. No fixture-only production exception.

Tests will cover unsigned metadata refusal, actual signed publication preserving all nine
members, signed invalid bytes despite cached measurements, changed proof/context/member,
no-overwrite and interrupted staging. Source and original candidates remain unchanged.
SD-C still owns studio job/revision/export binding and complete browser acceptance. These
are implementation requirements, not recorded passes or acceptance.

Fresh contrast map: SD-B-before-contrast-map.json captures detect_caption_ink_in_band
and references (probe_caption_ink, measure tests), plus new publication helper callers
before their fixes. White-on-black signed synthetic media exposed a 0.05 "contrast ratio":
whole-band 95th/10th percentiles missed sparse glyphs and used non-linear pixel units.
Real pixel regressions precede correction. Compute detected stroke versus adjacent surround
using the existing relative_luminance/contrast_ratio functions; do not lower 4.5 or fabricate
stored measurements. This corrects the observation shared by measurement callers, not
caption text, layout, golden references, fixtures or canonical ASR. Existing textured-
background/no-ink tests and actual decoded publication must still pass.

Private-staging adoption: SD-B-before-private-map.json records actual _flush_bound_artifact,
create/_validate and both render caller definitions/references before edits. Fresh review
roots and exclusive staging leaves are owner-private on Windows/POSIX; unsafe existing
roots refuse without repair. POSIX file modes may be set only on descriptor-bound, freshly
created renderer members in this exclusive leaf, never original candidate/source/trust.
Generic diagnostic seven-file packaging stays unchanged; proof-bearing publication remains
the fixed nine-file version. Tests/test_private_review_bundle.py precedes this correction.
Existing delivery promotion tests now use actual signatures/decoded media and assert all
nine unchanged files, or refuse every changed candidate member after a valid real baseline.
The new explicit unsigned/signed 30-byte regressions preserve the earlier counterexample.

## SD-A Implementation Map (2026-10-03)

SD-B portability follow-up: SD-B-type-portability-map.json re-resolves the descriptor-bound
flush helper and its ArtifactBundle._validate caller plus both changed delivery tests before
the Windows typing corrections. Runtime private-storage policy is unchanged. The existing
episode test definition/references are also recorded in SD-B-review-test-helper-map.json;
its unsigned test claim supplies schema-required reviewer fields, never a signature.

Subsequent SD-C boundary research: SD-C-before-map.json maps web POST/server setup,
prepared configuration/result projection, submission reserve/work directory, serial dispatch/
reconciliation, guarded billing, coarse worker/DBOS setup, manifest preview, source access
and raw-proof publication. HTTP generation is still refused until the protected worker is
connected; no job/revision/export integration pass is implied by this map.

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
