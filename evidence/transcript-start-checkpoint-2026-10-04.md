# Transcript Stage Reporting Checkpoint

Status: WIP; no task/feature completion or candidate verdict. Date: 2026-10-04 UTC.
Baseline HEAD fdfe25e8c80a58d95f312cbb0258808638f66552; tests run on explicitly dirty
source, not claimed as evidence from a committed candidate. Private evidence root:
C:/Users/Wareen/AppData/Local/HawEditEvidence/zar38-recovery-fdfe25-20261004/.

## Scope And Test-First Evidence

BLUEPRINT sections 2--5; approved parent T2 scope. Actual Serena definitions/references
are preserved in specs/evidence-based-studio/transcript-events-before-map.json and
transcript-alias-before-map.json; original private logs preserve LSP fallback warnings.
Only existing run_pipeline event placement and additive test_events regressions change.
The decoded native media drives the integration; the explicitly labelled observer producer
is a boundary double, not proof of ASR accuracy or actual model performance.

Commands: .venv/Scripts/python.exe -m pytest tests/test_events.py -q with each report
written by pytest to a distinct private --junitxml path. No selection, deselection or skips.

| Record | Tests | Failures | Errors | Skips | JUnit Seconds | SHA256 |
|---|---:|---:|---:|---:|---:|---|
| transcript-start-test-first.xml | 19 | 2 | 0 | 0 | 51.271 | 7fabc0656ad48731a7631c09854a450e0c17e365b0ab4daa92008fecd6b1252e |
| transcript-start-test-after.xml | 19 | 0 | 0 | 0 | 50.373 | 5d5d5f0dd1db8d3fccfa3630f0f42474d2193539736679abbbf5ce7d0a1adeeb |

Before source repair, the two new start-before-producer and operational-refusal tests
failed. The new cache-preservation test passed already. All original assertions remain.

## Host And Tool Identity

Measured on HawaPC01, Windows 11 build 26200, Threadripper 3990X, two RTX 3090 Ti,
274741166080-byte RAM; diagnostics use the CPU gate interpreter, not GPU model inference.
CPython 3.12.10 / MSC v1943 AMD64; SQLite 3.49.1, pytest 9.1.1, ruff 0.9.6,
mypy 1.15.0, DBOS 2.29.0, SQLAlchemy 2.0.52. Other workloads were active.
The event integration timing is not a performance benchmark.

.venv/Scripts/python.exe -m ruff format --check src/hawedit/pipeline.py tests/test_events.py
exited 0: both already formatted. Native C:/Program Files/Git/bin/bash.exe
scripts/verify.sh --fast exited 0, lint and strict typecheck over 315 source files.
The initial default bash invocation selected the Windows WSL shim and refused a malformed
Windows-lock path; transcript-start-fast.log preserves that failed attempt. No lock,
interpreter, gate command or enforcement source was changed to bypass the refusal.

## Caller Verification And Independent Risks

run_transcript_callers.py is exercising all fifteen complete mapped caller modules with
pipeline.py SHA256 667c3bcca93b0986b922839562006835ce83a6de894f51c0b67df7ec854d0b48
and test_events.py SHA256 5fd3274cf8669c6029e1ca9cc7e75587328ee7c6b29779a3d33254ca297bb23c.
Terminal result at 13:44:02 UTC: exit 0, source hashes unchanged, 575 tests, zero failures,
errors or skips. Wrapper elapsed 795.1594 s; JUnit reports 786.543 s. Report SHA256:
060edaffc9c56d959d6b1436da7ad21256e4134616d76664b7f79b90f84d1284.
Managed session 42914 closed only after exact native child absence. This is a complete
caller diagnostic, not the canonical full gate. Actual post-edit Serena mapping completed
at 13:46:18 UTC, six definition/reference queries, source hashes unchanged. The preserved
transcript-events-after-map.json binds the dirty files: run_pipeline has 190 references
(the four new test calls), unchanged affected files; the explicit test producer has three
construction callers in test_events. Imported file-symbol fallbacks remain in private logs.
Reviewed local commit and exact full scripts/verify.sh remain required. Same-SHA CI is not present.
No ledger promotion. The qualified VEX binding/expiry remains an independent full-gate
blocker; no review date or source hash is rebound.

Actual ZAR38 on the original frozen producer emitted 5853 aligned words plus three gaps
and two rejected corrections in 7814.9197 seconds including preparation/postprocessing.
The real first-gap reproduction emitted a 266-digit final token and reproduced frame
infeasibility. Those private evidence records retain original source/model/runtime binding.
This unit does not fix canonical quality, validate native meaning, authenticate publication,
authorize spending or clear the independent billing-admission P1. No useful-reel acceptance.
