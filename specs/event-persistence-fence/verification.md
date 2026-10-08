# Verification

HawaPC01/Windows26300/CPython3.12.10/pytest9.1.1/ruff0.9.6/mypy1.15.0/DBOS2.29.0.
No provider/model inference, delivered reel, performance/reliability acceptance
or same-SHA CI. Original source/canonical ASR not changed.

Test-first whole modules:

```
.venv/Scripts/python.exe -m pytest tests/test_event_persistence.py tests/test_studio_attempts.py --junitxml=C:/Users/Wareen/HawEdit-event-fence-test-first-20261008.xml -q --tb=short
```

49 pass / 7 valid behavioral failures / 0 errors or skips, 49.056s.
Raw JUnit39dad3255e3b7f112948a2999d8d5c7d51a700d3bf1dc96be0e303c55c4e1ff3.
Actual failed file writes, missing propagation, consumed invalid sequence and
SQLite lock error identity; no import failure, patched sink or disabled test.

Whole focused caller modules after repair:

```
.venv/Scripts/python.exe -m pytest tests/test_event_persistence.py tests/test_events.py tests/test_event_replay_integrity.py tests/test_run_cost.py tests/test_studio_attempts.py --junitxml=C:/Users/Wareen/HawEdit-event-fence-affected-20261008.xml -q --tb=short
```

97 pass / 0 failure/error/skip, 104.687s. Raw JUnit
781a9547ea1cd1fc0d762ba30da6351a696e4eff1f654f892928d3cd69f46236.
Full strict mypy363files, ruff check and format check pass. First static check
found a long new test signature; standard formatter fixed it without assertion
changes after the focused session ended. No test omitted or fixture/golden changed.

The repaired log fences any subsequent emission and preserves the original
cause. It is not a complete protected producer, sink durability proof, already
billed call refund, or authoritative scope/reconciliation record. Actual fatal
control-exception branch is source-reviewed, not a claimed OS signal experiment.

Current committed exact full gate must run before any ledger promotion. All
broader pipeline caller modules remain in that unfiltered suite; a focused pass
cannot speak for them. Qualified current VEX and same-SHA CI remain required.

First committed clean full gate at dfa455a: 5612pass/3fail/0error/skip, unchanged,
exit1. Terminal103f25de7f6f1b64fa19df082e7a47985b993113174e4ef491968149f72cb438;
JUnit8a7a089df58ce6238165741515c296c6c41fe377db9c69bbcfe7f3f132ff0b04.
Checkpoint caller expectation, denied private FFmpeg copy replacement, VEX
binding; preserved, not waived. Corrected checkpoint expectation retains every
seven-stage actual MP4 hash comparison and adds exact original cause/stage
checks. No product source change after dfa455a; producer stays fd72110b.

Expanded whole caller modules after that correction:

```
.venv/Scripts/python.exe -m pytest tests/test_event_persistence.py tests/test_events.py tests/test_event_replay_integrity.py tests/test_run_cost.py tests/test_studio_attempts.py tests/test_checkpoint.py tests/test_ingest_cache.py --junitxml=C:/Users/Wareen/HawEdit-event-fence-corrected-callers-20261008.xml -q --tb=short
```

119pass/0failure/error/skip,246.266s. JUnit
702f1d18bfa9739e93871c4689a65b6049a2eff8a3ef6a78e8068e30bf4a800a.
Full lint/format/strict types363files pass. Entire unchanged ingest-cache module
also independently repeated16pass; its earlier denied binary replacement remains
unattributed and is not claimed fixed. All cases remain in the full retest.
Exact committed full gate and CI still required; no ledger or release promotion.
