# Exact Projection Research

2026-10-03 baseline3d9f80ef97f7fa8aa2b08feaa17991dd6ccc2b04,
producer46479aef802e28ee129018a9d44c61452f1d36f437230943a603485559fffaa8.
Actual SQLite3.49.1 substr truncates at embedded NUL even when cap exceeds full length.
Copied private journals prove portable_json plus NUL/unknown suffix is admitted as its prefix;
copied outbox snapshot has1549 original bytes but1541 projected bytes and is also admitted.
Original successful diagnostic stores retained. No deserialization/DBOS launch/provider/model.
Raw counterexamples and copied stores: external studio-commit-3d9... directory, named
nul-projection-counterexample.json and outbox-nul-counterexample.json. The latter generator
retains its earlier generic unknown_nul_tag_admitted label; its actual scenario is outbox
snapshot bytes, not another serialization-tag test. Raw observed values disambiguate it.

The exact gate was intentionally interrupted after counterexamples, not completed/redgraded.
Verified main pytestPID64984 only plus its individually verified child if still matching;
no console event, source unchanged, exit127. Original log/exit/interruption retained. Canonical
report not fresh-complete; no terminal recorder, full-suite pass or task promotion claimed.

Actual Serena before-map: raw _read1/2, outbox _decode1/2,_select1/2 definitions/references;
_decode callers _get/_bounded_read, _select same pair. Reader callers _raw twice. All existing
get/reserve/pending/recovery/dispatch consumers keep signatures. Add original-byte length
equality checks before JSON; dispatch-state length metadata needed. Reject NUL diagnostics
before writing via note_dispatch_error to prevent a newly malformed self-produced row.
Exact bytes do not authenticate data, repair prefix-mismatched records or authorize work.
Pending selection includes invalid/null states for refusal instead of silently filtering them;
healthy confirmed records remain excluded. Actual fresh pending map1/29, diagnostic writer1/4.
UTF8/default SQLite text profile is required; other physical encodings are not implicitly adopted.
This is approved parent T3/D-276 correction, BLUEPRINT sections2-5, not scope reduction.
BLOCKED1/3/4/21/24/25, protected engine/lease/bootstrap/worker and full acceptance remain.

First red run:17 failed/115 passed/120.40s; map addition overlapped its documentation inputs,
so not claimed fully frozen. Unchanged frozen repeat:17 failed/115 passed/117.01s. Failure
inspection shows14 admission/writer failures and three CHECK-blocked setup cases, not17
behavioral demonstrations. First correction complete callers:313 passed/three CHECK-blocked
setup failures/194.52s. The corrected isolated test connection uses the existing intake test
convention ignore_check_constraints only to seed damaged persisted states; actual production
schema/CHECKs and every assertion stay unchanged. An overlong SQL literal is wrapped without
changing its bytes. Final fast lint/types pass; final complete callers and exact gate follow.
