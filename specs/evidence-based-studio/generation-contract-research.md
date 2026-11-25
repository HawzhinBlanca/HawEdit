# Generation Adapter: Source-Grounded Contracts

Prepared 2026-10-02, HEAD `372a16645d7a8558bc6cedcff34a9fbfa13f712f` plus T1 edits.
Research for approved T2/T3, not implemented behavior or accepted task completion.
No producer was constructed, model executed, cloud request sent or spend authorized.
Scope remains BLUEPRINT §§2-5, D-263, D-274 and the full approved seven-phase plan.

## Request Boundary

Preserve `/api/repurpose`, but version its request. Required source identity is the finalized
opaque `source_id`, not a filename/server path. Resolve actual bytes through UploadStore;
bind source digest and effective configuration before any durable submission. Reject unknown
fields, invalid enum values, booleans masquerading as integers and incompatible capabilities.
Persist client tokens; equal token/content reuses identity, changed content conflicts. Do not
expose transcript, verdict, QC, model, B-roll, logo or brand-kit server paths from browser input.
Those references require scoped uploaded assets or trusted local server configuration.

The current UI offers clip ceilings 1, 2, 3 and 5. Preserve those choices, not a guaranteed
number of outputs. Supported presets are broadcast, viral and split. Use real CaptionStyle
enum values/aliases from the shared parser rather than a second handwritten option registry.

Observed UI mismatch: `optCaptionStyle` emits `rtl_highlight`, while CaptionStyle and the
shared parser accept `rtl_word_highlight`. The current direct web conversion raises for that
selection. Add an explicit accepted-option regression and repair the frontend value when
adopting the shared contract; do not silently turn an unsupported value into another style.

## Shared Producer And Configuration Path

`pipeline.build_parser` plus `build_and_run` already resolves effective presets and constructs
ASR, discovery, judging, visual composer, temporal grounder, tracking and diarization. Durable
execution reconstructs this path from argv. The current web manager instead calls run_pipeline
directly without producers and forwards unsupported preset; replace that route, do not duplicate
the pipeline or serialize live clients/credentials into DBOS.

Parser-only observation (`shared-parser-contract-observation.log`) confirmed these effective
policies in host Python 3.12.10, without constructing producers:

| Preset | Captions | Silence threshold / target gap (ms) | Split | Hook banner |
|---|---|---|---|---|
| broadcast | broadcast_studio | 0 / 150 | auto | true |
| viral | rtl_word_highlight | 250 / 100 | auto | true |
| split | broadcast_studio | 0 / 150 | always | false |

Resolve the effective object for content-bound identity: omitted options must not silently
become explicit UI overrides defeating the preset. Include runtime/model/configuration
identities in provenance; credentials stay out of persisted argv, diagnostics and web responses.
Canonical ASR defaults to the champion per D-260, not an automatic stock fallback.

Generation defaults to production constraints and **private** review. In the inspected source,
production sets assembly, while `qc is None or not qc.human_reviewed` sets private review.
No browser-supplied QC record may authorize publication. The authenticated review and byte-bound
promotion boundary remains T6, not an unchecked boolean handed to the producer builder.

Model/readiness/security, diarizer access, actual discovery/judge route and cloud governance
must produce actionable prerequisite refusals before paid work. An API credential alone does
not authorize spending or transcript transfer. Local server configuration records an approved
route, confidentiality policy and budget; browser content cannot fabricate those approvals.

## Events And Results

RunEvent carries run ID, sequence, stage and started/completed/skipped/billed state. Timestamp
is not ordering; a billed event does not complete a stage. A replaying coarse workflow needs
attempt identity rather than globally deduplicating equal sequence numbers across attempts.
Do not retain the web manager's guessed 15/30/45/.../100 work percentages.

EpisodeManifest has all candidate items: selected, published, pending-review, failed, rejected.
Its clips collection alone is not the outcome denominator. Preserve refused/no-clip and partial
outcomes. `reconciled=True` or a nonempty manifest is not authenticated delivery evidence.
Only current reconciled, signature-bound publication can yield completed deliverables.

ClipMeasurement stores hash under `file.sha256` and duration under `video.duration_ms`.
The old web code reads top-level keys, then invents duration/quality on failure. Use the typed
measurement parser and verify its file binding. Missing measurements are unknown, not zero
converted to 45 seconds or a fabricated virality percentage. Editorial hook scores are judge
estimates, not measured audience performance or quality checkmarks.

## Sequential Implementation And Verification

Map each affected existing method/caller with Serena before source changes. Keep one writer.
Test the versioned boundary, producer parity, token conflicts, private review completion,
per-candidate refusal/partial outcomes, actual nested measurement and state-preserving replay.
Then wire the pinned DBOS queue before launch, concurrency one; do not replace the coarse
pipeline step or assume it reconciles ambiguous billing. Existing recovery/checkpoints remain
authoritative. Run the exact full gate after each implementation task. T1 is still unaccepted;
this research does not advance T2/T3 or close security, clean-build, CI or human evidence gaps.

## Implementation Boundary Selected

The request/preparation and report/event interpretation form a pure adapter needed by the
durable studio worker. Implement these first and immediately reject the old raw-path HTTP
route. New source-ID requests validate actual finalized bytes before a visible missing-runner
refusal; they must not fall back to the old daemon. This is a temporary, unaccepted integration
checkpoint, not a substitute for working generation. Next wire DBOS submission, durable client
identity and projections, then replace the legacy read/migration surface and adopt uploads
in the frontend. Do not claim any producer execution, publication or studio acceptance merely
because pure preparation/projection tests pass. Configuring a provider is not spending approval.

Independent clock observation: ffprobe 8.1.1 on the existing 48,021-byte fixture reports video
103 frames at 25 fps / 4.120000 seconds, audio and container 4.161995 seconds. Evidence:
`fixture-clock-observation.json`. The first new projection test incorrectly inherited the old
web mock's 4.16-second value; its expectation was corrected to the independently probed video
clock, not rounded to conceal an output mismatch. No fixture or renderer reference changed.
