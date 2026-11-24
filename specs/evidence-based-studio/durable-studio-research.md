# Durable Studio Integration Research

Observed 2026-10-02; HEAD `372a16645d7a8558bc6cedcff34a9fbfa13f712f`, uncommitted
package `122ca64f6b9665951b353e2ea9f3fd8a2355be0bfb354b200ef82bd662c0b41c`.
Research for approved T3, not implementation or acceptance. No model/cloud calls.

## Pinned Runtime And Caller Evidence

Installed DBOS 2.29.0 exports Queue and SetWorkflowID. Its `register_queue` takes
`concurrency` and `worker_concurrency`; both must be one for the approved local worker.
The current [official queue tutorial](https://docs.dbos.dev/python/tutorials/queue-tutorial)
uses `global_concurrency` instead. Do not copy that changed signature into the pinned runtime.
Queue registration persists configuration; inspect the returned values and refuse a conflicting
configuration rather than assuming an earlier queue has the requested limit.

Serena mapped six more definitions and callers, bringing `serena-map.json` to 64 records:

- `run_pipeline_workflow`: run_durable and the real DBOS cancellation test.
- `_run_pipeline_step`: run_pipeline_workflow; builds through the shared parser/builder.
- `VisualWorkflowRecoveryManager`: dependency enumeration and recovery tests, not the pipeline.
- `reconcile_external_billed_call`: recovery tests, not a production hosted producer.
- `GeminiJudge._post`: generate_json and judge_with_count.
- `GeminiJudge.generate_json`: PathADiscovery._discover_single and governance tests.

Existing durable tests prove real-library replay/dedup/cancellation behavior, with stub producers
for mechanism tests and separate actual-media cases. They do not prove no duplicate external
billing. Cancellation of the synchronous coarse step cannot forcibly stop the underlying call.
Startup recovery can re-enter the whole step. See installed DBOS source and
[workflow guidance](https://docs.dbos.dev/python/tutorials/workflow-tutorial).

## Billing And Recovery Gap

GeminiJudge._post attempts transport once and refuses ambiguous retryable/network results.
However its caller records BilledCall only after a response. A crash before that record leaves
no durable pre-request intent; coarse replay can repeat a request. The recovery manager and
reconciliation helper have no production pipeline call sites in the captured Serena map.
Their existence is not evidence that this gap is covered. The helper's caller-supplied string
ledger is not authenticated provider confirmation and must not become a UI approval shortcut.

Before enabling automatic replay of paid work, persist bounded intent/request identity before
transport, confirmed response evidence before continuing, and explicit uncertainty on failure.
Reuse verified responses where safe; uncertain outcomes require attributed reconciliation, not
a browser boolean or automatic retry. Spend limits need conservative reservations and a trusted
owner configuration, including confidentiality/rights. Credentials remain outside saved argv.
The shared producer construction must carry this control without a broad pipeline rewrite.

## Submission And Read Integration

The studio needs a SQLite submission ledger plus durable queue identity, not daemon bookkeeping.
Commit the request/token binding before enqueue; retry an interrupted enqueue with the same
workflow ID. A second ledger and DBOS database cannot form an atomic transaction, so reconcile
that boundary explicitly. Enqueue failure must not return a fictitious queued acknowledgement.
Same token/different effective content is a conflict. Revalidate actual source and resolved
model/runtime/governance identities at execution; preparation's package/config hash alone is
not yet the full worker identity.

Persist explicit attempts and immutable argv references. Derive reads from durable state and
validated events/reports; SUCCESS of generation means awaiting-review, never publication.
Label raw engine outcomes as unverified observations until authenticated promotion exists.
Preserve legacy records/media; mark historical completion unverified and interrupted work
reconciliation-required. Surface malformed persistence instead of swallowing it.

Required next tests: real DBOS queued concurrency/dedup and second-process recovery, SQLite
token conflict/reconstruction/storage failure, interrupted enqueue reconciliation, actual shared
producer wiring without live spending, pending paid intent refusal, legacy migration diagnostics.
These must complement, not replace, real-media and independent acceptance. No T3 row is closed.

## Selected T3 Submission Unit

Implement the SQLite request/token outbox and pinned DBOS queue together. A trusted caller
supplies an execution-binding digest after actual preflight; the store persists/binds that value
but does not certify models or owner authority from it. Request identity is recomputed from the
prepared source/config snapshot. Full workflow identity includes execution binding. Identical
content may share a workflow across client tokens; a reused token with changed binding/content
conflicts. Keep stored references immutable and bound JSON sizes. No credentials/live clients
cross the queue boundary.

Use SQLite BEGIN IMMEDIATE, foreign keys and full synchronous commits. Reserve before enqueue,
then record confirmation only after DBOS reports the correct identity/queue. Failure leaves
explicit submission-pending uncertainty, not false completion; retry the same ID to reconcile
the two-database boundary. Existing completed DBOS work must not be re-enqueued, including an
interrupted local acknowledgement. Persist queue concurrency one and refuse conflicting config.
Queue callback receives only job ID and must be a registered protected workflow. This unit does
not itself authorize paid work, certify its callback, replace the coarse engine or connect HTTP.
The producer worker, durable billing guard, preflight and read/migration adoption remain required
T3 integration; valid web generation remains refused until those boundaries exist.

Tests drive real SQLite and real DBOS, with bounded local probe workflows rather than model
substitutes claimed as generation. Cover token conflict/reconstruction, multiple connections,
malformed/unknown schema, immutable snapshots, storage failure, lost enqueue acknowledgement,
queue config conflict, serial execution and completed duplicate reuse. Extend EARS evidence
without treating mechanism tests as end-to-end completion. No enforcement file changes.

Implementation adds `studio_submissions.py` and `studio_queue.py`; the queue accepts only a
decorated workflow name, records/revalidates its job-ID-only input and persisted queue identity,
and reuses an already recorded execution instead of re-enqueueing completed work. A lost local
confirmation remains pending even when DBOS already ran the probe. SQLite failures are real
trigger/lock faults in temporary databases; the second-process test exits immediately after
durable enqueue with workers disabled, then recovers on another real DBOS process. This does
not exercise a crash inside model inference or prove exactly-once external billing.

Additional regressions first exposed monotonic-dispatch and dangling-token defects, repaired
without changing assertions. Native JSON decoder research on host Python 3.12.10 found 2,000
nested arrays parse despite the Python recursion limit of 1,000, whereas depth 4,000/16,384
refuses. `T3-json-decoder-observation.log` records that distinction. Initial malformed-record
tests failed to produce a native decoder refusal; they were corrected to an independently
observed bounded input, then reproduced unhandled RecursionError in read/preparation. Both are
now contextual errors without relaxing recursion or record limits. Earlier attempts remain
preserved. These observations are interpreter-specific, not editorial-quality measurements.

## Legacy Read Surface Refusals

`web.py` still serves `/api/status` with fixed `duration_s=48.14` and `audit_passed=True`,
independent of evidence. The durable read adoption must remove these claims, not merely add
truthful projections beside the old endpoint. Unknown GET paths also call
SimpleHTTPRequestHandler.do_GET. A real temporary loopback server returned HTTP 200 and
62,095 bytes for `/README.md` from the project root; response SHA-256
`145aaafe1abdd2e2f563c5d15d5c0ce52f1e7393e7f907fddc97a3def3f4420c`.
Evidence: `legacy-static-fallback-observation.log`. The server was shut down, no source changed,
and no secret or model was accessed. This proves unlisted filesystem serving, not a tested
secret disclosure. T4 must refuse unknown routes and whitelist local UI assets plus scoped
manifest artifacts. Add `test_studio_refuses_unlisted_filesystem_routes`; do not create/read
real secret files to test it. External Google font links remain an offline-rendering gap in T5.
