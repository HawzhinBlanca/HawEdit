# Owned Startup Caller Impact

Baseline80d6091329071ae281be1532c661002d793279c1. Actual cached Serena LSP
FindSymbolTool/FindReferencingSymbolsTool, completed before edits; full map and fallback
warnings preserved in owned-startup-before-map.json/log. Counts are tool observations.

| Symbol | Definitions/references | Change/caller obligation |
|---|---|---|
| inspect_studio_journal |1/26|Preserve signature, separate read-only transaction and all132 existing tests; share validation, not authority |
| _raw, _validate, _policy |1/1 each|Reuse exact schema/projection/JSON/outbox policy for same-connection inspection |
| _Budget |1/4|Preserve actual global raw count/byte/elapsed semantics |
| studio_private._identity |2/10|Function plus instance variable matched; reuse real function for descriptor identity, no private storage behavior change |
| PrivateDirectory.verify |1/25|Reuse native root/access fence; do not rewrite original permissions |
| PrivateDirectory.member_identity |1/17|Reuse actual member checks for lifetime lock |
| PrivateDirectory.open_new_file |1/5|Reuse exclusive private creation; permanent lease not removed |
| PrivateSqlitePath.verify |1/26|Reuse before/after native opens, transactions and private sidecars |
| SubmissionStore.recovery_snapshot |1/7|Same bounded immutable input reader; no schema/signature/budget change |
| configure_studio_queue |1/5|Existing CLI/test callers unchanged; actual serial persisted policy must agree with bootstrap |
| reconcile_studio_submission |1/2|Exercise existing ID-only dispatch through owned runtime, no duplicate enqueue publication |
| configure_dbos |1/22|Do not rewrite generic CLI durable path or foreign singleton |
| run_web_server |1/3|No HTTP runner injected; retain explicit unavailable refusal pending protected worker |

New module studio_runtime owns native lease, exact engine/bootstrap and runtime lifecycle.
New same-connection inspection API delegates exact existing raw validation but does not
own the caller transaction or change its progress handler/PRAGMAs. Tests cover existing
raw inspector, real owned runtime, dispatch/submission and private-storage callers.

Installed library APIs are actual source-inspected pinned2.29.0, not guessed:
SystemDatabase.create/run_migrations/upsert_queue, Queue constructor, DBOS config/launch/
destroy, registry internals, event-loop/executor/background-thread fields. SQLAlchemy
engine events and native connection access are verified in tests. No dependency edits.

After adding new symbols, run actual Serena definition/reference maps again before any
later adoption or change. File-scope LSP fallback is a mapping limitation, not proof of
absence. Existing raw/private/queue/generation/intake/claims/durable tests stay enabled.

## Fresh Implementation And Correction Maps

owned-startup-first-map.json/log: actual12 queries before changing lease, launch/close,
environment/registry/owner verification, engine statement/bootstrap/creator and subprocess
controls. owned-startup-dispatch-map.json/log: reconcile_studio_submission1/2,
SubmissionStore.note_dispatch_error1/5, runtime verify1/0 and constructor1/0. Storage
refusal now records a generic diagnostic independently in the outbox and rethrows; if that
write also fails, both failures are visible. Existing lost-ack/confirmed-duplicate callers
remain required and no job identity, confirmation, policy or queue signature changes.

owned-startup-typing-map.json/log: seven actual queries before native platform/type proof
corrections: StudioLease constructor1/0 and release1/5; engine begin1/1, commit1/1,
verify1/2; both native-decoder/VM-handler test functions1/0. Native driver proof is factored
from the existing begin check, reused before SQLite inspection; no cast/ignore or weakened
runtime assertion. Windows platform guards allow strict platform typechecking; POSIX
locking is not measured on this Windows host.

Subprocess runtime calls embedded in test_studio_runtime.py's Python string are a manual
dynamic-caller supplement: bootstrap, launch, verify, close and policy reconstruction;
foreign singleton/registry/constructor race, crash/resume, duplicate dispatch, draining,
held connection, contention, decoder and unsafe-row cases. LSP zero references does not
prove no dynamic caller. No HTTP or producer invocation is connected by these tests.
