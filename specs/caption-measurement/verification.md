# T1 Verification

Baseline: 79fc026b6d36cc2341892e5f17d87308a3756ff5. Native HawaPC01,
Windows 11 build 26300, Threadripper 3990X, CPython 3.12.10, pytest 9.1.1,
ruff 0.9.6, mypy 1.15.0. Source package after T1:
29e945b4c4f9c22cda86e43c0efedf534ffe288397cbbce49a731726eb3dd647.
These are development checks, not frozen full-gate, CI, throughput or release evidence.

## Red Before Implementation

Two initial missing-renderer/cache negatives failed with DID NOT RAISE at the
original implementation. Raw JUnit C:/Users/Wareen/HawEdit-caption-measurement-red-20261008.xml,
SHA256 1c51eff89da4b9b3ed62735eb2cdfcc4541d923a452a1256ea75ec4a86024ba6.
The initial whole new test module had ten failures, including the not-yet-present
decoded-extent helper. Raw C:/Users/Wareen/HawEdit-caption-measurement-all-red-20261008.xml,
SHA256 89d4d2d5cca7c137e3913c084153a89f11ffbc6d2c16756fb0edd02c8a322fec.
No subprocess/function mock or modified fixture/golden made these negative results.

## Affected Callers After Implementation

Actual command:

```text
.venv/Scripts/python.exe -B -m pytest tests/test_caption_measurement.py tests/test_captions.py tests/test_delivery.py tests/test_claims.py --junitxml=C:/Users/Wareen/HawEdit-caption-measurement-callers-20261008.xml -q
```

308 passed, zero failures/errors/skips, JUnit time 97.690s. Timestamp
2026-10-08T15:21:26.385402+03:00. Concurrency makes this diagnostic timing, not
isolated performance. Report SHA256
553ec8815dc55acbfe7ddf4b014572fe68922e088fd562ce2f5fa4ef22255214.
Tested captions.py byte SHA256
ebea28d031d7c6dc1084fcdeb72e6a82bb4b3911706eae6e26881bd2d79f9ade;
test_caption_measurement.py byte SHA256
50d49431e9cf2943f266c924b6ef6c9571d7ddde345df38222b89172f8460e2a.
Actual renderer and font hashes for the original genuine ZAR observation are in
research.md. Resource-negative tests use real configured FFmpeg, real local fonts,
an absent path, a real nonrenderer Python executable and separately copied fonts.
The pure invalid-extent parser test is not described as a rendered-media test.

All src/tests/scripts pass ruff check, strict mypy (355 source files), and ruff
format --check (355 files). No existing test, golden, model or harness was edited.
Bounded process-local cache descriptors are freshness observations, not held
resource authority or a defense against malicious same-privilege replacement.

## Still Required

Reviewed local commit and exact bash scripts/verify.sh with immutable observation;
genuine original ZAR surface retest; required same-SHA CI. T2 selected-font/canvas
forwarding remains unimplemented. No ledger promotion, completed-studio,
verified-publication, Kurdish fidelity or 10/10 claim follows from these checks.
The preceding frozen full gate at 79fc026 passed 5477/5478 tests and refused the
qualified current VEX binding (BLOCKED #24); do not rebind historical sign-off.
