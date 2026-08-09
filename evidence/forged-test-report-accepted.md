# A 30-line fake `pytest` printed VERIFY OK — and poisoned the committed floor on its way out

> Measured 2026-08-09 on hawapc01 against `64f440c`, against a green 1,155 baseline.

D-092 closed the case where `PY` was not an interpreter that runs this project. It could not close
this one, and said so: with a real `PY`, anything earlier on `sys.path` that answers to `-m pytest`
*becomes* the test step. Named as the next item in that commit; reproduced here rather than taken
from the adversarial-pass agent's report.

## Measured

A `pytest/__main__.py` on `PYTHONPATH` that parses `--junitxml=`, writes 1,200 `<testcase>`
elements, prints a plausible summary line and exits 0:

```
$ PYTHONPATH=<fake> PY=$PWD/.venv/Scripts/python.exe bash scripts/verify.sh
==> lint          All checks passed!
==> typecheck     Success: no issues found in 94 source files
==> format        94 files already formatted
==> tests         1200 passed in 61.50s   [forged, wrote .gate/last-test-run.xml]
==> test evidence test evidence OK — 1200 collected, 1200 passed, 0 skipped
VERIFY OK — hawedit gate green
exit=0 elapsed=4s

floor before: 1155
floor now:    1200
```

Four seconds, exit 0, zero test bodies executed. Lint, typecheck and format ran for real — only the
one step that produces the evidence was substituted.

**Freshness could not see it.** The `not_before` check exists for a leftover report; this report was
written during this run, by the thing pretending to be pytest. Layer 3's own reasoning — "exit code
is not evidence; the report is" — holds only while the report comes from pytest.

**The damage outlives the run.** `write_floor` ratcheted the committed floor to 1,200, so every
honest run afterwards would have been refused for a bar a forgery invented — a fake green that leaves
the gate permanently red. That is the same self-poisoning shape as the `collected`-vs-`passed` bug
already described in `gate.py`'s docstring, arrived at from the outside.

Never computed, not computed-and-discarded: no test body ran, and the counts were authored rather
than measured.

## The fix: provenance, not a list of hostile variables

```python
GATE_TOOLS: Final = ("pytest", "ruff", "mypy")
# each must resolve under sys.prefix
```

Enumerating ways to redirect an import — `PYTHONPATH`, user site-packages, a directory in the working
tree — is the same losing shape as the blacklist of no-op commands `gate.py`'s docstring already
describes. `sys.prefix` is where the interpreter's own packages live, so a tool outside it is not the
one the environment installed, however it got there. Nothing is chosen; the interpreter and the module
settle it between them.

Measured: `pytest`, `ruff` and `mypy` all resolve under `.venv` here and under `.venv` in CI.
`hawedit` deliberately does **not** — it is installed editable in both places, so its file lives in
`src/`, and requiring otherwise would refuse the only install layout this repo uses. That it imports
at all is proved by `-m hawedit.gate --check-tools` running.

Folded into D-092's existing probe rather than added beside it: one call, one refusal path, before any
step runs.

```
  PYTHONPATH=<fake pytest>  -> exit 3, names `pytest -> …\fakepytest\pytest\__init__.py`
                               floor unchanged at 1155
  PY=/usr/bin/true.exe      -> exit 3, unchanged from D-092
  honest --fast             -> exit 0, "fast checks OK"        <- CONTROL
```

## Mutation audit, against a baseline verified green first

```
baseline FAILED=0
CAUGHT   the provenance rule never fires (the defect)                    FAILED=2
CAUGHT   offenders are collected and then discarded                      FAILED=3
CAUGHT   a tool with no file falls through to Path(None)                 FAILED=5
CAUGHT   pytest is dropped from the checked tools                        FAILED=2
CAUGHT   only the environment's own tools are refused (over-strict)      FAILED=13
CAUGHT   verify.sh stops asking about provenance (D-092 only)            FAILED=1

6/6
```

Two of these are worth naming individually:

* **`pytest` dropped from `GATE_TOOLS`** is caught by a test that reads `verify.sh` and requires every
  `$PY -m <tool>` step to appear in `GATE_TOOLS`. A checked list that drifts behind the steps it
  covers is a hole the exact shape of the one being closed.
* **The last mutation** — reverting `verify.sh` to D-092's import-only probe — is caught by exactly
  one test, the end-to-end forgery. That is the test doing the real work.

The audit also reproduced the damage on its own: with the rule mutated away, the forged run inside the
test ratcheted the floor 1,161 → 1,200, which the "floor unchanged" assertion caught and which was
restored by hand before committing.

## What this does not close, precisely

A substituted **`hawedit`** itself. `--check-tools` would then be the forgery's own code, and no check
written in this module can outrank that. It is also a much louder thing to arrange than a directory on
`PYTHONPATH`: the shadowing package has to reimplement the gate's own API. Stated rather than implied,
because the cheapest version of this fix is one that quietly claims to be complete.

Gate: `VERIFY OK — 1161 passed, 0 skipped`.
