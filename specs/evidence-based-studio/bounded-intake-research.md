# Bounded Submission Intake Research

2026-10-03. Clean HEADbfc210e63d60a9ff799691c52d1993c2f15791c2,
producer3689baa16b8bf43afb03b4063d3882bb448f16eba49f5cf51e2ad3602a1c9ea3.
Approved parent T3 protected supervisor/recovery scope, BLUEPRINT sections2-5/D-276.
Read [[HawEdit pinned diarizer output checkpoint 2026-10-03]] in the central vault first.

SubmissionStore.pending currently constructs every decoded pending record with no row or
aggregate text budget. Its _select bounds snapshot/error strings but not job IDs, dispatch
state or malformed nonnumeric timestamps. Checking size after returning pending() is not
bounded intake. Recovery needs exact selected outbox IDs, including confirmed dispatch,
before checking pinned DBOS records without invoking their deserializers.

Five fresh actual cached Serena LSP queries are bounded-intake-before-map.json, not guessed
signatures. Definitions found once:pending17 references,_select2,_decode2,_get5,get10.
Actual native SQLite and private fixture roots are available. Preserve every original test,
actual outbox identity/token/acknowledgement and legacy CLI/queue signatures except additive
keyword-only pending budgets. No new runtime dependency, model or authorization policy.

Bound selected/returned rows and aggregate SQLite-encoded persisted text before decoding; refuse
overflow explicitly without losing/truncating jobs. Add SQLite VM progress deadline controls,
but never call those an absolute filesystem-I/O deadline or process-memory guarantee.
Normal lookups retain immutable identity and malformed-record refusals; bounded projection
must not turn an oversized or wrong-typed field into a valid record.

This is a prerequisite of actual startup, not replacement acceptance. DBOS all-surface raw
admission/private engine/lifetime lease/bootstrap/guarded worker/attempt/runtime/billing/
session/revision/export remain mandatory. Empty DBOS listeners do not pause internal work;
custom engines bypass normal SQLite connection settings. BLOCKED1/3/4/21/24/25 owner evidence
and the independent/sustained thresholds remain. No paid/model run or authority granted.

First complete caller diagnostic at prototype65b2c082...:113 cases,112 passes,one deadline
failure,zero errors/skips,68.454s. Actual CPython3.12.10/SQLite3.49.1 Windows clock metadata
reports monotonic GetTickCount64 resolution0.015625s; performance counter uses monotonic,
nonadjustable QueryPerformanceCounter resolution1e-7s. Preserve the short native deadline
and SQLITE_INTERRUPT assertion; correct the elapsed clock instead of lowering the test.
Raw clock observation and full diagnostic retained externally. Two further actual Serena
queries map _bounded_read2/recovery_snapshot5 references before clock/null correction.

SQLite also permits null TEXT PRIMARY KEY in this non-STRICT rowid schema; test that actual
malformed record before repairing the new byte arithmetic. No schema migration or data repair.
[SQLite primary-key documentation](https://www.sqlite.org/lang_createtable.html#the_primary_key),
[Python3.12 native SQLite progress callback](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.set_progress_handler),
retrieved2026-10-03. Actual native counterexamples remain stronger than API descriptions.
