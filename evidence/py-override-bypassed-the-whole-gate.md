# `PY` replaced all five gate steps, and the fifth was the one grading the other four

> Measured 2026-08-09 on hawapc01 against `ec6d38f`, against a green 1,151 baseline.

M0.1's row says the gate "refuses a no-op command instead of printing green", and `verify.sh` says
why that rule is a whitelist rather than a blacklist:

> No blacklist of ways to run nothing can be complete, so the rule is inverted: the gate's steps
> are not configurable. A replaced step is refused outright rather than judged on its content.

`LINT_CMD`, `FORMAT_CMD`, `TYPECHECK_CMD` and `TEST_CMD` are each refused with exit 5. `PY` is not —
it is a documented override ("PY still overrides for a deliberate interpreter"). And `PY` is the
prefix of all four commands **plus** the evidence step:

```bash
LINT_CMD="${LINT_CMD-$PY -m ruff check src tests}"
TEST_CMD="${TEST_CMD-$PY -m pytest --junitxml=$TEST_REPORT}"
run_step "test evidence" "\"$PY\" -m hawedit.gate \"$TEST_REPORT\" …"
```

So one variable that is not refused replaces every step that is.

## Measured

```
$ PY=/usr/bin/true.exe bash scripts/verify.sh
==> lint
==> typecheck
==> format
==> tests
==> test evidence
VERIFY OK — hawedit gate green
exit=0 elapsed=1s
report exists: NO
```

One second, exit 0, `VERIFY OK`, and **no JUnit report written at all**. Layer 3 exists precisely so
that "the exit code stops being the evidence" — and layer 3 was `true.exe`, auditing four other runs
of `true.exe`, using the single skill `true.exe` has.

This is *never computed*, not *computed and discarded*: nothing ran, and nothing was written for
anything to read back.

The likelier version of the mistake is not `true.exe` but another venv's python — a real interpreter
that simply does not have this project in it. Measured against one that exists on this box:

```
$ PY="…/hermes-agent/venv/Scripts/python" bash scripts/verify.sh
It answered: ModuleNotFoundError: No module named 'hawedit'
exit=3
```

## The fix

One probe, immediately after `PY` is resolved and before any step runs — the single point every path
(`--fast`, nested, full) routes through:

```bash
_probe="$("$PY" -c 'import hawedit; print("hawedit-interpreter-ok")' 2>&1 || true)"
if [[ "$_probe" != *hawedit-interpreter-ok* ]]; then … exit 3; fi
```

The shell checks the **value**, not the exit code, because an exit code is exactly what `true.exe` is
good at. The rule is stated as a capability rather than a spelling — the same inversion the override
refusal already uses — so it needs no list of things that are not Python.

Verified in five directions:

```
  PY=/usr/bin/true.exe                     -> exit 3, refused, "<nothing at all>"
  PY=/usr/bin/true.exe --fast              -> exit 3, refused (no "fast checks OK")
  PY=…/hermes-agent/venv/…/python          -> exit 3, quotes ModuleNotFoundError
  PY=/nonexistent/python                   -> exit 2, unchanged (order preserved)
  PY=$PWD/.venv/Scripts/python.exe --fast  -> exit 0, "fast checks OK"   <- CONTROL
```

## Mutation audit, against a baseline verified green first

```
baseline FAILED=0
CAUGHT   the probe never refuses (the defect)                          FAILED=3
CAUGHT   empty output reads as no objection (the D-091 shape)          FAILED=2
CAUGHT   every interpreter is refused (over-strict)                    FAILED=10
CAUGHT   the interpreter's own answer is swallowed                     FAILED=1
CAUGHT   the probe stops importing the project (any python passes)     FAILED=1

5/5
```

Stated precisely, because a mutation caught for an unrelated reason reads as protection it does not
have (D-082): the last two are each caught by **exactly one** test, the `ModuleNotFoundError` one, and
that is the test doing real work. The over-strict mutation is caught by ten, of which nine are
pre-existing tests of the gate's success path and one is the new control. **So unlike the previous
four iterations, the over-strict direction here was already covered** — the control makes the property
explicit rather than newly protected, and it would be wrong to claim otherwise.

The second mutation is worth naming on its own: `-n "$_probe" &&` is the exact shape of the defect
fixed one iteration earlier in `corpus_import.py` (D-091), where a truthiness clause turned "said
nothing" into "raised no objection". Here it would have let `true.exe` — which says nothing — straight
back through.

## What this does not close

A **forged report** is a separate hole and is not addressed here. With a real `PY`, something else on
`PYTHONPATH` answering to `-m pytest` could write a JUnit XML that layer 3 then reads back and
accepts; the probe cannot see that, because the interpreter really is this project's. Recorded as the
next item rather than folded in — it needs its own measurement, and it was reported by an agent, not
yet reproduced by me.

Gate: `VERIFY OK — 1155 passed, 0 skipped`.
