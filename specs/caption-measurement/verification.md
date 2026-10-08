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

## T1 Exact Frozen Gate Result

Local-only commit e1f07fec2e46b3cc01f17ff0a07c693018daa64a, package29e945b4c4f9c22cda86e43c0efedf534ffe288397cbbce49a731726eb3dd647.
Exact bash scripts/verify.sh exited1:5489passed/5490tests,1failure,0errors/skips.
Lint/strictmypy/format355pass. Caption measurement12,captions131,delivery98,
claims67 all pass in the frozen report. Sole failure: historical qualified VEX
source binding81f6f606f89115ddedcba38941aad0b3f86cc59187a52b21b2a8a4f609bc5eba
differs from current package; BLOCKED #24, do not edit/rebind old sign-off.
All tracked source/controller/HEAD/package/status unchanged and checkout clean.
Actual controller/raw logs/report:
C:/Users/Wareen/AppData/Local/HawEditEvidence/caption-measurement-full-gate-20261008.
JUnitSHA256ed1f04e5e5b90498fef2dd95c08eee782dafdae1c2950b4708bfe3ca8baba151;
terminal.jsonSHA2566dfa3ac445a4712a15b4d20fae9f7c7d93222f6a9a42c423827babe2a8f736dc.
Finished2026-10-08T13:04:28.824654UTC, JUnit2313.924s/controller2321.9640109s,
concurrent diagnostics, not isolated product performance. Native hardware/tool
versions above; DBOS2.29.0. Exact children absent before session15617 closed.
No successful gate grading, same-SHA CI, ledger promotion or release verdict.

Genuine original aligned ZAR word retest at this commit, same renderer/fonts:
absent-first/actual-first both refuse missing renderer and actually measure94px.
Raw C:/Users/Wareen/HawEditCaptionWidthRetest-e1f07fe-20261008/terminal.json,
SHA256120ec5fa13a37cf91d77b7573dc679ab8312c31a1793d3b791834a588bb4c3c1.
Tracked source/observer/HEAD/package/raw/fonts/renderer unchanged, no new reel.

## T2 Development Caller Verification

Selected font name/size/directory and both canvas dimensions now reach all five
chunk calls, the line wrapper and both explicit RTL position branches. Existing
direct positional arguments/defaults and char-only/SRT semantics are preserved.
tests/test_caption_context.py adds29 actual renderer regressions. After strict
typing identified the existing dynamic invalid-limit dictionary, actual Serena
mapping preceded spelling out its unchanged three zero-limit refusal assertions.
No fixture, golden, harness, dependency, canonical transcript or model changes.

Whole caption-context/measurement/captions/delivery/claims modules337pass,
0failures/errors/skips, JUnit106.768s (diagnostic, not isolated performance),
C:/Users/Wareen/HawEdit-caption-context-callers-repaired-20261008.xml SHA256
b89d7eee6f60a8bb800331d35513fb0befc2f11083e474cbd827f2dea0ffcecf.
Whole ruff check/strict mypy/ruff format --check pass356 source files.
Reviewed local-only commit and fresh exact frozen full gate/ZAR consumer retest
follow. Same-SHA required CI and qualified current VEX remain unproved. Both task
rows stay WIP; no verified-publication, accepted reel or completed-system claim.
