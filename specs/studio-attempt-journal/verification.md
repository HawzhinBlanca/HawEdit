# Local Diagnostics, Not Acceptance

2026-10-07, HawaPC01 / Windows11 build26300 / CPython3.12.10,
pytest9.1.1, ruff0.9.6, mypy1.15.0, installed DBOS2.29.0. Dirty candidate
based on c5504ef88e8bca7ac3c8484e2838783d82b867c2; no paid provider call,
production inference, publication or full-system readiness claim.

Initial exact module run before implementation:34 missing-module failures,
0 errors/skips. Raw external attempt-journal-test-first-20261007.xml. Separate
initial34-case and extended47-case actual module diagnostics passed. Initial
E501 and SIM105 lint failures were retained and repaired without exemptions.

Entire affected modules command:

```powershell
.venv/Scripts/python.exe -B -m pytest tests/test_studio_attempts.py tests/test_studio_execution_input.py tests/test_studio_generation.py tests/test_studio_submissions.py tests/test_studio_private.py --junitxml=C:/Users/Wareen/AppData/Local/HawEditEvidence/attempt-journal-callers-20261007.xml -q
```

Actual166 cases passed,0 failures/errors/skips; JUnit106.357 seconds. This includes
real private-media upload, immutable outbox preservation, actual SQLite lock
contention/concurrent reservations, committed process-exit persistence and
uncommitted process-exit rollback, strict corruption and private event projection.
The Sorani text is a test string, not a transcript/accuracy measurement.

JUnit SHA256:b55244d4f0904360c287b060073de5128e25ec23ae48834a86fead2b8bb364ba.
Watched source at diagnostic completion:
- studio_attempts.py:4e05149220cb826be64c71e54fd9b1fa4624c79c138d7ec24b3b91cd43820100
- test_studio_attempts.py:3dd482612d6dfeafb804ab08d734f6f5089371802f759171ab27b6a856c2dff4

Ruff check, format check and strict mypy for both new files passed. These are
diagnostics, not the canonical gate. Reviewed local committed source must run
exact bash scripts/verify.sh with an immutable external controller, then retain
its actual result/SHA/hash/host/versions. Previous c5504ef full gate was RED on
current-source VEX mismatch; do not copy its success counts into this candidate.
Qualified current VEX and same-SHA CI remain required; task/PROGRESS stay WIP.

Next protected worker adoption must consume this real journal, not describe it
as proof of model readiness, signatures, budget settlement or child quiescence.
