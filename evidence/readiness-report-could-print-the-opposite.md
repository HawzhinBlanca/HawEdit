# The report an operator reads could print the opposite of the truth, with 1,175 tests green

> Measured 2026-08-09 on hawapc01 against `3384647`, against a green 1,175 baseline.

D-099 made `hawedit.models` classify a downloaded-but-unloadable checkpoint honestly. That fixed the
*statuses*. It did not touch the renderer, and the renderer is what a human actually reads —
`readiness_report` is the answer to "can this machine run the pipeline", and it is the artifact whose
`OK` led M1.4's row to conclude the wrong thing in prose.

## Measured

Mutating the renderer alone, against the whole suite:

```
baseline FAILED=0
GREEN — nothing notices   every component prints OK regardless of availability
GREEN — nothing notices   the verdict is inverted
GREEN — nothing notices   the summary count claims everything is available
GREEN — nothing notices   the size disappears from every line
RED (5)                   the missing list is emptied, so nothing is named
```

The report could print all fifteen components as `OK` with six missing, or invert every verdict, or
claim `15/15 available`, and the suite stayed green.

The one RED is the more interesting result. Its failures were
`test_the_gpu_modules_typecheck_with_the_gpu_extra_absent` and two nested-gate tests — mypy objecting
to `missing = []`, not anything checking the report. A mutation caught for an unrelated reason reads as
protection that is not there (D-082), and here it was the only signal in five.

## Why the existing tests were blind

Two tests touched the renderer, and both asserted substring presence over the whole document:

```python
assert "omniASR_LLM_7B_v2" in report
assert "available" in report
```

`"available"` occurs in the summary line — `9/15 available` — no matter what the marks say, and every
model id occurs on its own line whether that line reads `OK` or `MISS`. The same shape as D-094's
`"hewler" in payload`, which the coverage block satisfied seven times over while the accuracy section
was gone.

## The fix

Assert the verdict **on the component's own line**, by finding the row containing the model id and
reading its first token, and assert the summary against the counts it summarises. Both directions are
pinned on the same function, because the measured defect was an inversion — a renderer that always
prints `OK` passes every all-available test, and one that always prints `MISS` passes every
all-missing test.

**A second defect surfaced while writing the test for the size column**, and this one was in the
source:

```python
size = f"…" if status.size_bytes else ""        # before
size = f"…" if status.size_bytes is not None else ""   # after
```

A checkpoint directory holding only empty files is non-empty, so it reports **present** with a
measured size of `0` — and the falsy check printed no size at all, which is the same line a pip
component gets and reads as "no weights here to measure". Measured zero and unmeasured are different
facts, and this repo's rule is that the second is `None`. The test for it failed first, then passed.

## Mutation audit, against a baseline verified green first

```
baseline FAILED=0
CAUGHT   every component prints OK regardless of availability            FAILED=2
CAUGHT   the verdict is inverted                                        FAILED=2
CAUGHT   the summary count claims everything is available                FAILED=2
CAUGHT   the missing list is emptied, so nothing is named               FAILED=2
CAUGHT   the size disappears from every line                            FAILED=2
CAUGHT   a measured zero is treated as unmeasured again                  FAILED=1
CAUGHT   the missing clause is appended even when nothing is missing     FAILED=1

7/7
```

Every one is now caught by a test that names the property, including "the missing list is emptied",
which previously produced only mypy failures in unrelated gate tests. The last two are each caught by
exactly one test — the measured-zero case and the dangling-`missing:` control — and the seventh
mutation exists because that control was otherwise unexercised by the set, which would have left an
assertion nothing had ever put pressure on.

`readiness_report`'s own output on this machine is unchanged in substance: still `9/15 available`, with
the same six named.

Gate: `VERIFY OK — 1181 passed, 0 skipped`.
