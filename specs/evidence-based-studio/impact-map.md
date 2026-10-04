# Caller Impact Map

Baseline SHA: `372a16645d7a8558bc6cedcff34a9fbfa13f712f`. Serena output: `serena-map.json`.
Complete affected method reference lookup before editing an existing symbol; class-level
references alone are not proof of method coverage. Refresh mapping when adding a unit.

| Boundary | Callers / obligations | Regression surface |
|---|---|---|
| New upload store | web POST/PUT, browser file submission | bytes/length/probe/capacity/duplicate names/restart |
| JobInfo / JobManager | global manager, web handlers, tests/test_web.py | migration/persistence/idempotency/stage truth |
| HawEditWebHandler POST/GET | ThreadingTCPServer, MockSocket tests, studio JS | source-ID API/path refusal/HTTP bounds/artifacts |
| build_parser / build_and_run | CLI main, durable_workflow, planner, tests | effective preset/producer parity; no signature change intended |
| durable_workflow | durable CLI, workflow_control, agent execution, tests/test_durable.py | preserve CLI; studio queue/register before launch |
| PipelineRun.complete | report serializer/CLI/recovery | do not loosen; render does not mean publication |
| promote_candidate / reconcile_delivery | pipeline/proposals/episode/resume/delivery tests | trusted authenticated envelope, unchanged bytes |
| QcRecord | clip parsers, QC proposals, pipeline, delivery tests | legacy fields insufficient at web trust boundary |
| DASHBOARD_HTML | GET root, source selection/settings/poll/review/seek/export | responsive/RTL/focus/history/context/errors |
| Acceptance evaluators | acceptance kits/scorecards/release reports | independent clusters, signed evidence, no boolean attestation |

No changes intended to canonical transcript storage, ASR model policy or frozen blueprint.
Before changing a shared producer, delivery, reviewer, or recovery symbol, extend this map
from its actual Serena references and add tests for every affected contract.

## Captured Method References (2026-10-02)

Serena completed definitions and references for all existing JobManager methods being
changed, JobInfo/to_dict, HTTP POST/GET, shared parser/builder, delivery and QcRecord.
`submit_job` callers: HTTP repurpose; tests/test_web.py job execution, failures and
idempotency; tests/test_robustness_audit.py two-source, rapid-submit and restart tests.
`get_job/get_all_jobs/to_dict` callers: GET handlers and those two test modules.
`update_job_caption`: POST caption edit only. `_save_job`: submission, caption edit and
all execution/event branches. `_load_persisted_jobs`: constructor. `_run_job_stages`:
submission and run_job_sync. HTTP methods are invoked through stdlib request dispatch,
which LSP cannot expose as direct references; MockSocket tests and server handler binding
cover that contract. No shared pipeline/delivery signature will change in the upload unit.

## Champion Security Research Extension

Five additional Serena definition/reference lookups completed on the continuation's unchanged
source package `52d23b1833eb3d761b4a6781a60ac43bd66b2cdca1b45fa1fc05c273bbebc8f0`, bringing
`serena-map.json` to 28 records. No ASR symbols were edited.

- `OmniAsrBackend._load`: `transcribe_segment`, `align_segment`, two loader-control tests.
- `_load_adapted_llm`: the adapted branch of `_load` only.
- `resolve_champion_adapter`: `_build_and_run` and missing/partial/override bundle tests.
- `create_omni_asr_producer`: `_build_and_run`, explicit runtime-selection and invalid-bundle
  tests; public exports/imports are also recorded by LSP.
- `asr_worker.run_request`: worker CLI main and worker, validator, lease and adapter tests.

Any future verified-descriptor repair must cover initial transcription and re-alignment,
stock and champion construction, worker transport, bundle provenance and default resolution.
Existing stock-only tests cannot evidence the adapted loader. See the security review packet.

## Upload Hardening Callers

Before the next T1 repair, four further lookups brought the map to 32 records:
`UploadStore._record` feeds reservation accounting, receive, describe and source;
`begin` feeds POST and store tests; `receive` feeds PUT and real-media tests;
`_request_length` feeds JSON-body parsing and PUT. These definitions were captured on the
`52d23b...` source before its malformed-record/length repair. New named regressions are
`test_upload_malformed_record_fields_are_contextual_refusals` and
`test_upload_http_extreme_content_length_is_a_refusal`; existing real-media, restart and
HTTP tests continue to cover the affected public callers. The shared filename validator is
new and serves both reservation input and persisted records to prevent contract divergence.

## Upload Recovery Callers

Before response-loss repair, Serena added `describe`, `source`, `_write`, `_local_write`
and the store constructor. `describe` feeds receive/source; `source` feeds real-media,
restart, corruption and HTTP tests; `_write` feeds begin and all receive state transitions.
The constructor creates each isolated store and the global web store. `_local_write` guards
POST/PUT; GET recovery will reuse that conservative loopback/same-origin boundary because
successful reconciliation writes a ticket. HTTP GET remains stdlib-dispatched and is covered
through the existing request harness. Existing `_record`/receive caller maps also apply.

New status/reconciliation helpers must preserve source validation for all existing callers.
Regression coverage uses real decoded fixture bytes and injects only the final atomic ticket
write failure, not a mocked probe/hash/source. Cases include lost response, prepublication
interruption, committed-but-unacknowledged media, mismatched metadata, changed bytes,
unavailable persistence, expired reservation and guarded HTTP errors. No shared producer,
job manager, ASR, fixture, golden or enforcement symbol changes in this T1 extension.

The recovery helper `_validated_source` was additionally mapped before its type repair:
callers are status reconciliation and source resolution. The map now contains 38 records.

## Generation Contract Research Extension

Five further definition/reference lookups bring the map to 43 records, without producer
source edits. `resolve_effective_configuration_from_args` feeds the shared builder and preset
override tests. RunEvent/to_dict feeds JsonlEventSink and roundtrip tests; RunEvent itself
feeds event logs, checkpoint replay, cost reporting and durable execution tests. ClipMeasurement
feeds measurement, delivery reconciliation/promotion, both pipeline delivery paths, cover and
measurement/delivery tests. EpisodeManifest feeds PipelineRun, episode delivery/reconciliation,
serialization and partial/no-clip tests. `generation-contract-research.md` records the actual
nested measurement and per-candidate contracts to preserve in T2/T3. Method-level maps must
still be refreshed before modifying any additional method; class research is not that proof.

## T2 Request And Projection Boundary

Serena captured the shared HawEditArgumentParser/build_and_run export and all six legacy
HTTP tests whose filename/server-path assumptions change; the map now has 51 records.
Existing POST handler maps remain applicable: stdlib dispatch and web/robustness request
harnesses call it. No JobManager, pipeline, durability, measurement or event signatures change.
The new module delegates to the shared parser/resolver and emits argv for the existing
durable builder, never a second producer implementation. Report projections consume typed
measurement/episode contracts and verify actual bytes; they cannot authenticate publication.

New named tests cover source/path/option refusal, semantic preset identity, shared producer
argv, literal option values, private render state, missing/altered evidence, episode outcomes
and state-preserving event sequence. HTTP refusal is integrated now; durable accepted submission,
client-token persistence, migration, queued execution and projection adoption remain the next
sequential unit. Legacy fake-card HTTP success assertions are replaced by stricter no-enqueue
and real source-ID prerequisite checks; no tests, goldens or fixtures are skipped or weakened.

Five new adapter/projection lookups and subsequent `_parse`/validate_source maps brought the
evidence to 58 records before repairs. `validate_source` feeds preparation and HTTP POST;
the tuple return reuses its validated path so preparation does not hash a 32 GiB source twice.
`_parse` feeds request option validation and full prepared argv. It uses an isolated shared
parser with exit_on_error disabled, not process-global stderr redirection in concurrent HTTP
handlers. Candidate/result helpers feed projection tests; the independent duration expectation
was corrected only after separate ffprobe evidence identified video/audio clock divergence.

## T3 Durable Worker Research

Six additional Serena lookups bring the map to 64 records. `run_pipeline_workflow` feeds
run_durable and cancellation tests; `_run_pipeline_step` feeds that workflow. Any adaptation
must retain CLI behavior and those real DBOS tests. Recovery manager/reconciliation references
are confined to recovery helpers/tests, not production paid calls. GeminiJudge._post feeds
generate_json and judge_with_count; generate_json feeds Path A and governance tests. Adding
durable billing controls must cover discovery, judging, Developer API/Vertex inheritance,
governance refusal and response-loss cases, preserving existing single-attempt semantics.
No durability, recovery or producer source changed during this research. Detailed findings
and pinned/current DBOS API differences are in `durable-studio-research.md`.

## T3 Submission Mechanism Callers

Before repairs, Serena mapped six new store symbols and seven queue/test symbols, then the
bounded SELECT/StoredSubmission and deep-record regressions, bringing evidence to 81 records.
Store reserve feeds the queue adapter and identity/concurrency/storage regressions. Decode
feeds get/pending and reservation/update validation; dispatch update feeds confirm/error
methods and acknowledgement recovery. SQL selection feeds get/pending. Queue configure feeds
reconciliation and persisted-limit tests; submit feeds real DBOS probes and a second-process
probe. Reconciliation feeds submit and explicit future recovery. Status validation feeds only
reconciliation. Test helper complete feeds probe completion checks. No existing web, producer,
coarse durable workflow or recovery signature changed in this unit.

New callers introduced by regressions also require late-error monotonic confirmation and a
contextual missing-snapshot refusal for dangling tokens. The deep JSON regression must first
prove the native decoder's recursion refusal, rather than merely rejecting a deeply nested
wrong root type. Source/record hashes, bounded diagnostic reads and atomic rollback remain
obligations for every outbox caller. An execution-binding digest is persisted data, not a verified
readiness verdict; adoption must provide actual protected preflight and paid-call controls.

## Protected Producer Research Extension

Five additional records bring Serena evidence to 86. Gemini count_parts feeds discovery and
HTTP/governance/key tests; judge_with_count feeds judge and authoritative count/token-ceiling
tests. build_visual_composer feeds the shared builder/device tests. Constructor-method maps
return no LSP callers, so their class references/direct construction must also be mapped before
changes. `protected-worker-research.md` records the existing transport injection hook and why
input-only estimates cannot enforce an output-inclusive spending ceiling. No shared producer
signature or source changed in this research; no provider was called.

## Guarded Transport Implementation Callers

Serena now has 92 records, including GeminiJudge/VertexGeminiJudge class constructors,
Transport, native _https, shared _run_from_args and existing external reconciliation errors.
The unchanged _build_and_run definition/reference map remains applicable. Its callers are
_run_from_args (CLI), durable_workflow._run_pipeline_step (DBOS) and parser/producer/refusal
tests in test_pipeline, test_content_type and test_durable. Add only optional keyword-only
judge_transport; preserve both existing positional arguments and default no-injection behavior.
Constructors retain their signatures. PathADiscovery uses the same judge client; K defaults
to five repeated identical requests, so content-only response caching would fabricate votes.
Use deterministic per-content occurrence identity on replay; preserve distinct first-attempt
egress. Default builder validations remain unchanged; no new argv refusal is introduced.

New private journal callers are the guarded transport and native SQLite/loopback regressions.
It must validate source/job/policy identities, route, bounded request/response JSON, configured
output and thinking caps, provider input count and conservative integer reservations. Confirmed
responses may be reused without egress, but an intent without a confirmed response blocks
further billed calls for that job. Policy pool consumption spans jobs and remains reserved after
uncertainty or confirmed calls; it is not an actual provider invoice. No existing recovery helper
is treated as authentication: boolean reconciliation remains insufficient. Trusted policy/runtime
verification and operator reconciliation precede production worker/API enablement.

The mechanism repair maps bring evidence to 107 records. Guard constructors check recognized
schema before journal-mode changes; native storage regression preserves foreign/versioned bytes.
Reservation validation checks bound identity and arithmetic across the shared authorization pool,
not only the current job. Expiry is rechecked after counting and immediately before generation.
New builder regressions use actual decoded fixture frames, existing bound manual transcript
data and a loopback protocol provider; this is not model inference or semantic quality evidence.
PipelineRun.editorial is a skipped-state field, not a JudgeVerdict slot. Corrected the new test
from that inspected contract: successful judgment is in the clip, while delivery stays refused.
Large-input case IDs are short on Windows; unchanged payloads still exercise full bounds.

The final preflight research brings Serena evidence to 116 records. Actual signature/file
binding, Vertex environment, WSL receipt/runtime and producer-device maps ground the next
adoption unit, not source edits to those helpers. The ASR WSL bridge does not move visual
producers to WSL; runtime checks must target the actual worker. Canonical judge transport
injection does not reach GeminiFlashScreener/JevScreener, which the same builder constructs
separately. Their paid/confidentiality controls must be mapped and repaired or explicitly
refused before protected execution is enabled. No caller coverage is claimed for that open
integration. All 44 billing, 23 submission, seven queue, 29 generation and 38 upload cases
passed in the latest canonical report; the full gate remains red for build/VEX prerequisites.

## T4 Read Boundary Callers

Serena has 125 records. do_GET is dispatched by the HTTP base class and exercised by web,
upload/generation and robustness tests. The current class inherits filesystem do_HEAD, which
must not survive the switch to BaseHTTPRequestHandler. _json_reply serves existing write/read
refusals and will suppress content for HEAD. _local_write guards upload/generation; retain its
call sites and extend strict single Host/origin validation to explicit reads and legacy edits.
Constants FONTS_URL/DASHBOARD_HTML feed HTML tests; ALLOWED_MEDIA_EXTENSIONS currently feeds
recursive media lookup, which is removed rather than reused as authorization.

Affected legacy tests retain their names and strengthen the approved contract: status must not
invent quality; served-media/review-directory and RB-15 must use decoded measured media and
explicit job report manifests; the legacy pipeline bundle test must not treat its fake report
as authorization to serve an unscoped URL. Existing JobManager/CLI behavior is not rewritten
here. New studio_artifacts callers are the handler and native file/HTTP regressions; root/job/
clip validation, stable bounded records, media snapshots and range parser are tested directly.
No delivery-engine signature changes, fixture/golden changes or new runtime dependencies.

Font packaging inspection found Vazirmatn absent from wheel data and SBOM. Its embedded name
table identifies OFL-1.1 and Copyright 2015 Vazirmatn Project Authors, matching the pinned
upstream v33.003 notice. Preserve the existing binary; add notice/provenance to data-files and
release-required members, and a distinct font SBOM package/CONTAINS relation. Existing
_spdx_sbom callers are release assembly and test_release. _release_source is the inline tiny
test package builder, not a protected canonical fixture: extend its asset inventory using the
real new shipped files, preserving every existing file/assertion. font_bytes uses the existing
RECORD-authenticating installed-data resolver when no source asset tree exists. Missing or
mutated source assets must not silently fall back to an installed font. No resolver signature
or enforcement-script change. Actual clean release/install remains blocked by dirty source/CI.

The attribution generator also needs the new non-model font in registry.SHIPPED_ASSETS;
do not widen BLUEPRINT's canonical model registry. Serena maps the asset inventory and
attribution_notices callers, including the bidirectional README/notice checks. Existing
OFL licence objects/obligations are reused; no licence assertion is relaxed. A new staged
copyright notice absent from HEAD makes the existing Git archive test refuse: preserve
that evidence until a genuine commit/CI exists, rather than bypassing or weakening the test.

## Historical Read Adoption Callers

Serena has 157 records. Extract the existing _record JSON decoding into a shared bounded
snapshot reader without changing _record's existing three-value return or open_preview
callers. The new public reader only accepts job/report kinds and validated job IDs; its
callers are studio_history and native file tests. Existing snapshots/font/range tests remain.
HawEditWebHandler.do_GET adopts fresh persisted historical projection for jobs/detail/status
and an additive /api/history diagnostic envelope. /api/jobs remains a list; /api/status
preserves unavailable runner/latest-reel fields. HEAD stays body-free. Existing API job tests
and four status cases must now seed real job.json, not count unpersisted memory as durable.

do_POST's edit_caption branch adopts bounded strict JSON and refuses revision_required instead
of calling JobManager.update_job_caption. Its existing test preserves the name but now asserts
non-mutation and explicit refusal under the approved burned-in editing contract. Direct
JobManager tests remain unchanged: this unit does not certify or rewrite that legacy runner.
New history tests cover exact preservation, record/folder identity, unsupported fields/types,
native malformed JSON, link refusal, bounded/truncated scans, visible storage failures,
manifest-only candidates, sanitized source metadata and refreshed disk reads. No caller may
infer verified publication or execution from a historical flag or supplied JSON value.

Native bounded deep-JSON probes reproduced uncaught RecursionError in the shared _read_json
reader for uploads, generation and edits. Its Serena map brings evidence to 171 records.
Retain exact size/header checks; translate native decoder recursion and read transport errors
to contextual UploadError without changing recursion limits, request bounds or caller success
semantics. All three HTTP write routes plus existing upload/generation regressions are affected.

## T5 Studio UI Callers

DASHBOARD_HTML is read by HawEditWebHandler.do_GET for GET/HEAD / and /index.html, and imported
by test_web and test_robustness_audit. Preserve that public name by importing the extracted
studio_ui constant into web.py. Stronger semantic/state assertions replace checks for obsolete
marketing stage names and direct video-as-export assignment, without removing the regressions.
New HTML-parser tests inspect unique IDs, associations, initial unavailable states, local assets,
native controls and request/recovery contracts. They are structural checks, not browser execution.
Frontend callers use /api/status, /api/history, selected /api/jobs/{id}, guarded upload reserve/
PUT/status and manifest-scoped preview HEAD/GET. Existing backend/native HTTP regression groups
remain unchanged. No handler, producer, publication or revision signature change is required.
Browser actions must establish actual upload/recovery/history/settings/error/media behavior;
unavailable generation/revision/review/export are explicit gaps, not accepted end-to-end work.
## T3 Private-Journal Adoption

Existing changed symbols: studio_billing.GuardedGeminiTransport.__init__, _connection,
_call (Serena definitions/references in serena-T3-private-journal.log). Constructor callers
are the test guard helper, slow_count expiry test and embedded abrupt-child program;
the latter is inspected literal source, not claimed as a resolved LSP call. Every one is
covered by the unchanged billing assertions plus new storage/privacy regressions. No paid
production adopter currently exists. Reuse windows_security helpers without edits to their
model_fetch/vertex_acceptance callers. New journal-specific private binding is adopted only
by guarded billing, not misrepresented as all studio storage or HTTP authentication.

File/behavior impact: new studio_private.py and test_studio_private.py; mandatory journal
checks in studio_billing.py; actual private inline fixtures in test_studio_billing.py.
New files require README module-map and PROGRESS WIP entries before pytest collection.
Keep all 44 old billing cases' real SQLite/loopback/crash behavior and assertions. Legacy
unsafe owner files are preserved/refused, not repermissioned. Gate, goldens, fixtures,
model assets, secrets and frozen BLUEPRINT are untouched; D-276 records the extension.

Fresh final mapping: serena-T3-private-final-map.json captures 21 current definitions/
caller records without cached skips. PrivateSqlitePath constructor is called only by
GuardedGeminiTransport and native tests; verify is called by its constructor, billing
connection/request/result fences and native tests. _verify_binding is used only by
verify, twice around ephemeral sidecar checks. _send is called by all three upstream
routes in _call. The path property preserves actual read callers; no setter caller was
found. Test helpers and Windows junction assertions use Python 3.11-compatible APIs.
The abrupt-child string and standalone POSIX probe are inspected separately; LSP does
not resolve calls inside a string, and nonproject probe callers are not hidden adopters.

## T3 Private Upload/Outbox Adoption

Pre-edit mapping: private_storage_serena.py / serena-T3-storage-before-map.json (27 records).
New private helper definitions/references were mapped before adoption in the accumulated
serena-T3-storage-new.log (221 records); _probe and its substitution test were mapped before
the media repair (223-record serena-T3-storage-probe.log). storage_adoption_serena.py gives
fresh 42-record definitions/references for this integrated unit; import/file-symbol fallback
diagnostics are retained, not described as resolved containing functions.

StudioStorageError moves to the leaf private module and is explicitly re-exported from
studio_submissions. Actual catchers in billing/queue/outbox/web/native tests keep one class;
the real old test-only pickle and current roundtrip prove old qualification compatibility.
PrivateSqlitePath constructor now reuses PrivateDirectory without changing the existing
SQLite sidecar/billing rules. Its callers are billing, submissions and native private tests.

New PrivateDirectory and private atomic writer are adopted by all upload I/O and submission
work_dir allocation. Each UploadStore instance binds tickets/incoming/sources identities;
native root/member substitutions and metadata hardlinks refuse before continued operations.
SubmissionStore fences opening/commit/close with the mandatory SQLite binding; its queue,
generation and storage tests keep all original immutable-token/dispatch/recovery assertions.
Generic atomic_fs.write_text_atomic is unchanged. Only the upload fault-injection callback
imports the adopted private writer, preserving the same actual final-ticket OSError fault.

_probe callers are UploadStore.receive and native post-probe substitution testing. Suffix-
specific demuxers and measured format aliases affect all seven supported upload formats;
the full upload/generation groups plus real remux/decode positive and mismatch cases cover
them. No producer, transcript, codec dependency or model policy is changed.

Web's POST upload/generation, PUT upload and GET upload status use _upload_store and catch
storage refusals. run_web_server initializes the private upload leaf only after loopback
validation; import leaves UPLOAD_STORE unset. Existing HTTP fixtures explicitly provide
real private storage. New native children exercise actual configured/default startup and
real HTTP bytes; their program strings are manually inspected because LSP cannot resolve
embedded calls. The legacy JobManager remains unaccepted, not a private authoritative
writer or a worker. Original jobs/media/uploads are neither moved nor repermissioned.

tests/studio_test_storage.py provides genuine isolated private leaf/file creation, not a
mock for the checks under test. Four old fixture families (uploads, submissions, queue,
generation) retain their original domain assertions. New test_studio_storage.py requires
README module-map and PROGRESS WIP coverage before canonical collection. No protected
harness/golden/fixture, gate output, model asset, secret or frozen BLUEPRINT was edited.

## T8 Paired Comparison Data

Fresh serena-T8-paired-before-map.json contains 19 actual definition/reference records.
PairRating and RaterSubmission callers are validate_ratings, analyze_study, QC export,
comparison tests and public imports. StudyMetrics is returned by analyze_study and read
by its comparison tests; no other runtime consumer was found. Forms/Markdown retain
existing Sorani rubric labels and gain explicit A/B scope. Their callers are the formatter,
public exports and form tests. export_to_qc_records retains its signature but refuses
preference-derived approval; the existing integration test asserts this stronger contract.
wilson_score_interval also feeds compute_visual_scorecard's naive reference interval;
run that complete group and preserve existing valid-95% numerics. No visual_scorecard
authority claim is deemed repaired by this helper change. Imported file symbols and LSP
containing-symbol fallbacks remain explicit. Preserve historical diagnostic specs probes.
paired-comparison-plan.md records PC1-PC7 and the inherited approved implementation scope.
No new dependency, model policy, frozen spec, gate/golden/fixture or publication change.
New test_comparison_contract.py requires README and PROGRESS WIP mapping before the gate.

Final fresh 25-record mapping is serena-T8-paired-final-v2-map.json. OptionRating is used
only by PairRating's paired construction/validation, its serialization and validate_ratings;
from_options is called by the parser and new native tests. schema is read by submission
validation/serialization. No new runtime adopter or QC/producer signature change was found.
Mixed studies retain vote/paired counts but do not select the known subset for whole-study
differences. Current focused comparison/visual/claims run passes 120 cases without skips;
the earlier full affected run also exercised all signed editorial acceptance cases. The
canonical frozen run still determines current-source full-unit evidence, not these checks.

## T8 Acceptance Authority Guard

Actual serena-T8-authority-before-map.json contains 18 definition/reference records,
including each existing test changed by this unit. AcceptanceScorecard and its serializer
feed aggregate factory, scoped/sustained serialization and the editorial tests; scoped/
sustained helpers/reports feed those tests and immutable diagnostic probes, with public
exports checked separately. No production engine admission caller was found. Signed-study
CLI preparation/evaluation and the real signature verifier are unchanged. VisualScorecard
authorization/serialization feed the visual helper test, public exports, the factory and
diagnostic probe; no authenticated release consumer was found. Actual map fallbacks to
imported file symbols remain recorded, not invented symbol callers.

acceptance-authority-plan.md records AG-1-AG-6 and inherited owner implementation scope.
Tests preserve original count/refusal/numeric/leakage/signature assertions, strengthening
only false-acceptance expectations. New tests cover type/floor/construction bypasses and
explicitly nonauthorizing descriptive serialization. Existing diagnostic files are preserved;
new replay output receives new filenames/source identities. Add README/PROGRESS mappings
for test_acceptance_authority.py before canonical collection. No protected harness, fixture,
golden, model, dependency, paid route or immutable blueprint change. Positive authenticated
admission and the full original plan remain required subsequent work.

## T2 Transcript Start Placement

Baseline actual LSP maps: transcript-events-before-map.json (five definition/reference
queries) and transcript-alias-before-map.json (public builder alias), bound to clean fdfe25.
File-symbol fallback warnings remain explicit in private original logs.

- run_pipeline: 186 references across pipeline.py, web.py, test_checkpoint, test_episode,
  test_events, test_ingest_cache, test_pipeline, test_render_boundary_revision,
  test_render_caption_revision, test_review_findings, test_run_cost and test_screener.
- _build_and_run: 13 references in pipeline.py, test_content_type, test_durable and
  test_pipeline. Public build_and_run alias: eleven references across durable_workflow,
  test_pipeline, test_screener_integrity and test_studio_billing. Builder signatures stay
  unchanged; durable_workflow's secondary alias is not changed by this unit.
- RunEventLog: twelve references in events.py, pipeline.py, test_events and test_run_cost;
  started: sixteen references; finished: thirty-four. Their implementation/signatures stay.

Changes: pipeline.py start/operational-skip placement and additive native-media event tests.
Preserve completed order, enum/sequence/skip reason, raw immutability, config and cache keys.
Run all listed caller test modules, not a selected green subset; exact full gate remains
required. No real-model accuracy, progress percentage, cloud execution or publication claim.

Actual post-edit transcript-events-after-map.json completed at 13:46:18 UTC: six queries,
dirty source bound by unchanged file hashes. run_pipeline now has 190 references, the four
new integration calls in test_events; affected files are unchanged. _EventTestProducer has
three constructor references there. Method/test entrypoint reference queries are empty;
pytest discovery, not an invented symbol caller, executes the named regressions. Complete
fifteen-module caller run passed 575 tests, no failures/errors/skips. Exact full gate and
applicable same-SHA CI remain independent requirements; this is not task completion.

## T3 Whole-Journal Billing Admission

Actual billing-admission-before-map.json: eleven definition/reference queries, clean ff3411b;
billing file hash is unchanged at the later 0dd96f5 baseline. Original LSP fallback warnings
are preserved privately. GuardedGeminiTransport has thirteen references, including
SignedStudioTransport._journal and native test constructors; BillingPolicy twelve.
_existing has two, _pool_used two, _send three, _call one and _validate_response two.
Constructor-method references are empty; class references close that mapping gap.
guard and LocalProtocol each have 32 references across billing and screener-integrity tests.
The existing storage-outage test has no symbol callers; pytest discovery executes it.

Change only studio_billing's native evidence/admission boundary and its actual native tests.
Preserve SignedStudioTransport/public policy/build_and_run signatures and existing alias maps.
The UPDATE outage moves to a real upstream response callback, retaining one local generation,
an uncertain intent, failed persistence and refused replay rather than weakening the test.
Complete billing/authorization/private-storage/screener-integrity and shared-builder callers
are required. This is not authenticated protected-worker adoption, invoice evidence or VEX.

New helper admission map completed 15:19:49 UTC before adoption into existing methods:
seven actual LSP definition/reference queries in billing-native-helper-map.json. _native_rows
has three references in _inspect_journal; _validate_usage one; _inspect_journal one in
_inspect; _inspect has three native host-budget test calls. Stored-call/snapshot/budget
references are within this same module. Source hash was unchanged during the map.

The complete first implementation run exposed the deadline case on native Windows.
billing-deadline-before-map.json completed 15:23:57 UTC before correction: check nine
references, interrupted one, _inspect twelve, _inspect_journal one, _send three. Native
CPython 3.12.10 monotonic uses GetTickCount64 at 15.625 ms resolution; perf_counter uses
monotonic QueryPerformanceCounter at 100 ns advertised resolution. Preserve the failed
deadline test and use the latter for elapsed-time admission, without mocking the clock.
Only existing _send callers receive its optional private intent identity; public callable,
SignedStudioTransport, BillingPolicy and shared-builder signatures remain unchanged.

Final billing-admission-after-map.json completed 15:27:07 UTC: nineteen actual LSP queries,
source/test hashes unchanged. GuardedGeminiTransport fifteen references; BillingPolicy
seventeen; _existing two; _pool_used one; _send three; _call one; _validate_response one;
_inspect twelve; _validate_usage two; _native_rows three; _inspect_journal one; budget check
nine and progress callback one. guard forty-eight and LocalProtocol forty-two references
remain in billing/screener-integrity callers; _billing_bytes sixteen native test references.
Test entrypoint and constructor-method references remain empty with discovery/class mapping
explicit. Original imported/file fallback warnings are retained, not counted as assurance.
