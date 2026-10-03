# Bounded Intake Verification

2026-10-03, approved parent T3 prerequisite, not accepted supervisor/worker or release.
Source/test/docs were frozen during every diagnostic. Seven actual Serena queries precede
initial source and new-helper corrections; raw original/correction maps retained in this spec.

## Actual Diagnostics

| External XML prefix (all suffix -20261003.xml) | Source producer | Cases / passes / failures | Seconds |
|---|---|---|---:|
| bounded-intake-red | 3689baa16... unchangedbfc210e | 29 / 3 / 26 | 22.940 |
| bounded-intake-prefix-red | 3689baa16... strengthened valid-prefix tests | 29 / 3 / 26 | 22.873 |
| bounded-intake-focused-first | 65b2c082... prototype | 113 / 112 / 1 | 68.454 |
| bounded-intake-null-red | 65b2c082... added null counterexample | 30 / 28 / 2 | 23.566 |
| bounded-intake-focused-final | f31e3514... clock/null correction | 114 / 114 / 0 | 68.814 |
| bounded-intake-prefetch-red | f31e3514... added isolated prefetch counterexample | 31 / 30 / 1 | 25.022 |
| bounded-intake-incremental-final | ec31dca3... incremental collection, all final tests | 115 / 115 / 0 | 71.725 |
| bounded-intake-commit-focused | ec31dca3... final normal real-upload fixture plus claims module | 182 / 182 / 0 | 78.851 |

Every run:zero errors/skips. Exit0 only for the114/115/182-case all-pass diagnostics; others exit1.
Five complete final modules:test_studio_intake.py,test_studio_submissions.py,
test_studio_storage.py,test_studio_queue.py,test_studio_generation.py. Additional native
SQLITE_INTERRUPT assertion and valid-prefix/null/prefetch controls are not retroactively
claimed for earlier test-body versions. Original assertions/fixtures/goldens/harness unchanged.
Final producerSHA256ec31dca39c4f109b206b239f299017df66d750eb1f42efe00b20f01be2789623.

The original fast check refused a fixture-import name collision and one long SQL test line.
Remove the cross-test fixture import using the repo's ordinary real-byte upload/preparation
fixture pattern; split the identical SQL literal. No assertion changed. The182-case run
includes that final fixture and all67 documentation claims; the earlier115-case record is
the prior fixture body, not retroactively relabelled. Corrected exact verify.sh --fast exits0
(lint/strict mypy311); ruff format --check src tests scripts reports311 already formatted.
Those are diagnostics, not the full gate. Both fast logs preserved alongside the XML files.

Raw logs/XML are in C:/Users/Wareen/AppData/Local/HawEditEvidence; XML SHA256:

- red:d505701cd6e1161c6bdcdc61854a1f3e2fadefa9fdc192684dac8c46037ecf5f
- prefix-red:2704f572a0f9c845db2be8e443c0290734161b71e0ac2a7983c9b89e2dda9af5
- focused-first:d655d3b80111c49b623fac4ac5745de30212b7a5935089b29b860208bd080bda
- null-red:185c5394de3e8b8b4e729f435e6804a47985ec6acd0a8a4718740003df045bda
- focused-final:e3fa1e9f5ee42a1441034b433824f93964950fb8ba8f45b1ee2ff0982f045c9b
- prefetch-red:e329f405f0b55c1d3d6a056443ec88eaef38239422d1c82bf7225303ddcb1bb1
- incremental-final:cdb6d15c1a046f8300ebeb2b29a819beac93f2ca79c99892e2928d78194bf2d4
- commit-focused:26540f38ad102176b6e80b48ae0a88d4eed12a0d36b39c6678853ec90e91e5c2

## Scope And Runtime

Recorded native HAWAPC01/Windows11build26200/CPython3.12.10MSC1943AMD64/SQLite3.49.1/
pytest9.1.1/DBOS2.29.0/ruff0.9.6/mypy1.15.0. Recorded Threadripper3990X64cores/128logical,
RAM274741166080 bytes; these suite times are observations, not calibrated product latency.
Real private ACL/storage, decoded/probed upload fixture, native DBOS inert serial/restart
mechanics and an isolated CPython tracemalloc child run. No canonical ASR/real pyannote/
LLM/judge/vision or paid provider, runtime/licence/billing authority or publication acceptance.

Clock observation is bounded-intake-clock-observation-20261003.json at65b2c082...:
monotonic GetTickCount64 resolution0.015625s; nonadjustable monotonic QueryPerformanceCounter
resolution1e-7s. Keep the short deadline/real interrupt assertion; no assertion weakening.
Bulk-prefetch prototype's measured child Python heap is4,859,458 bytes on this runtime.
Final isolated counterexample passes the1MiB Python-heap control. It does not bound SQLite
native heap, total RSS or blocked filesystem I/O. SQL VM progress is checked every1000
instructions and after row collection; it is not an absolute preemptive-I/O timeout.

Current defaults:1000 jobs,16MiB aggregate original SQLite-encoded ID/snapshot/diagnostic text,
5s native query progress deadline. Maxima:10000 jobs,256MiB,10s. Count/text checked before
accumulating each projected row, and JSON decode deferred until the accepted batch is complete.
Overflow refuses without silently omitting work; damaged data stays intact. Exact selected
IDs include confirmed dispatch; duplicate/missing/malformed IDs refuse. No DBOS deserialize.
The normal newly created store uses UTF-8; SQL CAST-to-BLOB length tracks the database's
actual encoding. These budgets are not an assertion that a foreign database is UTF-8.

## Required Next Evidence

Reviewed local commit, clean frozen exact bash scripts/verify.sh, qualified current VEX and
applicable same-SHA CI. No policy rebinding, ledger promotion or push. M9.55 remains WIP.
Actual all-surface raw DBOS admission, owned private engine/lifetime lease/bootstrap and
guarded ID-only worker with attempt/runtime/billing/session, then immutable render revision,
authenticated review/reconciliation/export and all independent/sustained thresholds remain.
Generation still refuses studio_runner_unavailable; parent goal and scope remain intact.

## Oversized Integer Deadline Correction

The localb85ed735d238c8f061e575da900359fd8ce459d2 exact full gate was interrupted after
new genuine invalid-input evidence, not completed or claimed green. Verified pytest child
PID66032 only was stopped2026-10-03T18:02:01.4716495Z using Stop-Process, without a console
event. No live descendants were listed. Wrapper exit127; original log/interruption/exit
records remain in its external studio-commit directory. No fresh complete JUnit is claimed,
and the terminal recorder was not used to relabel the old canonical report as this run.

Fresh actual Serena _bounded_read definition1/references2 precedes the correction;
bounded-intake-deadline-map.json preserves pending/recovery_snapshot caller context. BI3
regressions add positive/negative10**1000 on the real private fixture. On oldec31dca...:
33 cases,31 passes,2 expected failures,zero errors/skips,26.477s,exit1. Both failures are
math.isfinite OverflowError before the upper-bound check. Red external XMLSHA256:
0350b4bf9e86f76a941d7ee2caf7e50ed44bf0421502dc74074ba133de821964.

Only the range/finiteness check ordering changed; no limit, assertion, fixture or caller
contract was weakened. Corrected producerSHA256
691e77160ee1548216a052c574578dca93a5b9237eabf53845219b05e7de3b1e.
Complete caller modules plus claims:184 passes,zero failures/errors/skips,83.437s,exit0.
XML bounded-intake-large-deadline-final-20261003.xmlSHA256
a89d08a3e0050f5b23ab3b283da6bc31b57997135f1aca4efcf007af5e64ad00.
Native CPython3.12.10/SQLite3.49.1/pytest9.1.1/DBOS2.29.0 on recorded HAWAPC01 Windows26200;
timing remains diagnostic, not product-performance evidence. Final exact --fast exit0
and format check311 passed. All source/test/doc inputs were frozen during these runs.
Replacement reviewed local commit and clean frozen full gate/current qualified VEX and
same-SHA CI remain required. M9.55 is still WIP; all broader adoption/acceptance stays open.
