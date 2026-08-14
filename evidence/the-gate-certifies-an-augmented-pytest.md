# The gate certifies an augmented pytest

> Measured 2026-08-13 on HawaPC01 against `3b83897`. Windows 11, Python 3.11.15, pytest 8.3.4,
> the repository's own `.venv`.

`src/hawedit/gate.py:64-70` states the rule it enforces: "Refuse a gate whose tools were
substituted from outside the interpreter's environment … with a real `PY`, anything earlier on
`sys.path` that answers to `-m pytest` becomes the test step." D-093 records the attack that
motivated it — a 30-line fake `pytest` on `PYTHONPATH` that printed `VERIFY OK` having run
nothing, and moved the committed floor 1155 → 1200.

That hole is closed. The neighbouring one is open: the check asks where `pytest` came from, never
what `pytest` then loads.

## A nine-line plugin turns a failing suite green, and the provenance check still passes

`GATE_TOOLS` (`gate.py:59`) is three module *names* — `pytest`, `ruff`, `mypy` — each verified to
live under `sys.prefix` (`:62-111`). A pytest plugin is none of those three names. It is imported
from wherever `sys.path` points, and it can rewrite the outcome of every test.

Three tests, one of them genuinely failing, graded by `python -m hawedit.gate`:

```
############ 1. HONEST RUN ############
FAILED test_thing.py::test_three - assert 1 == 2
1 failed, 2 passed in 0.19s
REFUSED: 1 failed, 0 errored out of 3 collected.
gate exit=6

############ 2. SAME COMMAND + two environment variables ############
--- gate.py --check-tools (the provenance guard) ---
hawedit-interpreter-ok
check-tools exit=0
--- pytest, identical command line ---
3 passed in 0.17s
--- gate.py grading the forged report ---
test evidence OK - 3 collected, 3 passed, 0 skipped
gate exit=0
--- floor after ---
3
```

The two variables are `PYTHONPATH=<dir>` and `PYTEST_ADDOPTS="-p forge"`. The plugin:

```python
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    out = yield
    rep = out.get_result()
    if rep.outcome == "failed":
        rep.outcome = "passed"
        rep.longrepr = None
```

## Why every downstream check is satisfied

Nothing here is a forged artefact. Real pytest runs, under the gate's own unmodified `TEST_CMD`,
and writes a real report with a fresh timestamp and a complete body. So the freshness check passes
on a genuine timestamp, the counts are internally consistent, and `scripts/update-ledger.sh:88-97`
finds every cited test name in it because those tests really did run — they merely did not really
pass. `gate.py:18` says "Exit code is not evidence; the report is." The report is not evidence
either, once a plugin decides what goes in it.

`scripts/verify.sh:69-95` refuses overridden steps, and its message says the gate's steps are not
configurable. `PYTEST_ADDOPTS` reconfigures the test step without being an override of it:

```
grep -rn "PYTEST_ADDOPTS" scripts/ .github/
  (no occurrence)
```

## The positive control, so the check is not maligned

The provenance guard is real and correctly specific. Substituting the module itself is still
caught, through the identical call:

```
PYTHONPATH=<dir containing pytest/__init__.py> python -m hawedit.gate --check-tools
REFUSED: these gate tools do not come from this interpreter's environment
  (C:\Users\Wareen\Desktop\HawEdit\.venv): pytest -> ...\shadow\pytest\__init__.py.
check-tools exit=7
```

## Scope, stated so this is not read as worse than it is

CI does not inherit a developer's environment, so `.github/workflows/gate.yml` is unaffected and
remains what AGENTS.md says it is: the only thing that means done. What is forgeable is the
**local** claim — and the local claim is what `scripts/update-ledger.sh:78` consults before
flipping a ledger row, and what AGENTS.md step 3 tells an agent to act on. An agent that can set
an environment variable in the shell it runs the gate in can flip rows on evidence that looks
authentic in every respect the harness checks.

The floor does not betray it either. A forge that only converts failures to passes leaves
`passed` equal to the count that would have been collected anyway, so `gate.py:246`'s
`evidence.passed > floor` is false, `write_floor` never runs, and CI's
`git diff --exit-code -- scripts/test-count.floor` has nothing to see.

## Addendum — the report's body is not evidence either

Measured the same day, on the same commit. `gate.py` reads only the `<testsuite>` summary
attributes; it never counts `<testcase>` elements. A report with **zero** of them:

```
  testcase elements in the file: 0
  --- gate.py grading it ---
  test evidence OK - 1659 collected, 1659 passed, 0 skipped
  gate exit=0
  floor after: 1659        (it was 2 before)
```

On its own this is not reachable: `scripts/verify.sh` deletes `.gate/last-test-run.xml` and
regenerates it, so no window exists for an outside writer — which is why an adversarial reviewer
correctly refused to call it a defect. That refusal assumes one writer.

Two facts in this repository undercut the assumption. BLOCKED #12 records that two sessions share
this checkout, and `.gate/last-test-run.xml` is shared mutable state between them. And the
companion measurement in `the-guards-path-boundary-is-inert-on-windows.md` shows the PreToolUse
guard does not stop a native-path write to that file — during the audit that produced these
records, an agent wrote to it with the Edit tool and the hook did not fire.

The harm shape is D-093's, verbatim: a graded count with nothing behind it ratchets the committed
floor, and "every honest run afterwards is refused". The floor is tracked, so CI's
`git diff --exit-code -- scripts/test-count.floor` would see the poisoned value — this is loud, not
silent. Recorded because it removes a layer of defence-in-depth that the design otherwise has.

## Not measured

Whether a plugin loaded via an installed entry point (rather than `-p`) behaves the same; whether
`pytest`'s own `--trace-config` or the loaded-plugin list would give `gate.py` a cheap way to
close this; whether the same route exists for `ruff` and `mypy`. No fix is proposed here — this
file records the measurement only.
