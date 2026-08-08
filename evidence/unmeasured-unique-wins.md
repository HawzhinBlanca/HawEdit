# §8.2's collapse metric reported a zero for a measurement that never happened

> Measured 2026-08-09 on hawapc01 against `d081dd8`.

§8.2's collapse test is stated in the blueprint as *"If Path B never surfaces a winner Path A
missed, collapse it."* `path_unique_wins` is the number that answers it. For a gold set with no
winners — a set nobody has annotated, or one where no clip was judged a winner — it returned:

```
recall_at_k         -> None
recall_at_k_by_path -> {}
path_unique_wins    -> {'verbal': 0, 'visual': 0, 'both': 0}
```

The same input, three metrics, two of them saying *unmeasured* and one saying **every path found
nothing unique**. A reader acting on that third line deletes Path B: GPU 0, a segmented 4B
checkpoint, and the whole of §3 Stage 3's visual half — on the strength of a number that came out
of an empty measurement.

This is the project's own hard rule — *unmeasured is None, never 0.0* — holding in one half of a
metric pair and not the other.

## Reproduced both ways

Nothing was measured (no winner in the gold set, and an empty gold set):

```
--- gold with NO winner (nothing was measured) ---
  recall_at_k         -> None
  recall_at_k_by_path -> {}
  path_unique_wins    -> {'verbal': 0, 'visual': 0, 'both': 0}      <- the defect
--- gold set EMPTY (nothing was measured) ---
  recall_at_k         -> None
  recall_at_k_by_path -> {}
  path_unique_wins    -> {'verbal': 0, 'visual': 0, 'both': 0}      <- the defect
```

Something *was* measured (one real winner, retrieved only by the verbal path):

```
  recall_at_k_by_path -> {'verbal': 1.0, 'visual': 0.0, 'both': 0.0}
  path_unique_wins    -> {'verbal': 1, 'visual': 0, 'both': 0}
```

That second block is what makes the fix narrow. `visual: 0` there is **the finding** — it is
precisely the evidence §8.2 wants for collapsing a path — so the answer cannot be "stop reporting
zeros". The two cases had to be told apart, and they were not.

## The fix, and why it is `{}` rather than `None`

`recall_at_k_by_path` already answers this question for a by-path mapping: **empty means
unmeasured, non-empty means measured and every path is present with its real value, zeros
included.** `path_unique_wins` now does the same. One line, no signature change, no caller
changes — `grep` finds no production caller at all, only its own module docstring, `discovery.py`
prose and the tests.

`None` was considered and rejected: it would have made the two halves of the same metric pair
disagree in *shape* while agreeing in meaning, and `recall_at_k`'s `float | None` is the right
signal for a scalar rather than for a mapping. Matching the sibling is the smaller and more
consistent change.

## Controls

`test_a_measured_zero_is_still_reported_for_every_path` asserts the measured case keeps all three
paths with `visual == 0`. That is the control that matters: `return {}` unconditionally passes the
unmeasured test and fails this one. The existing
`test_path_unique_wins_answers_the_collapse_question` (which already asserted
`[DiscoveryPath.VISUAL] == 0` on a real winner) was a second control that had to keep passing, and
did.

The new test also asserts the *pair* agrees — `recall_at_k is None` and `recall_at_k_by_path == {}`
for the same input that yields `{}` here — so the three cannot drift apart again silently.

## Mutation audit, against a baseline verified green first

```
baseline: GREEN
CAUGHT   unmeasured reports a zero for every path again (the original defect)
CAUGHT   the unmeasured branch is removed, so an empty gold set divides by nothing
CAUGHT   a measured result drops paths that found nothing unique

3/3
```

Run over `tests/test_repurposing.py` **and** `tests/test_discovery.py`, because
`test_discovery.py` also calls `path_unique_wins` — a mutation that only the discovery tests
noticed would otherwise have read as unprotected.

## Where this came from, and what it says

Found by the 2026-08-09 adversarial pass (`evidence/adversarial-pass-2026-08-09.md`), which
attacked ten DONE rows and falsified 19 claims. M7.1 is one of the rows that had no evidence file
at all — its Definition of Done listed six metrics and the ledger cell listed the same six back,
so the row was self-certifying. The defect is not that a metric was missing; all six exist. It is
that one of them answered a question nobody had asked it.

**Still open from that pass, on this row:** `iou_match` is accepted unvalidated, so a caller
passing `1.5` or `-1` gets silent nonsense instead of a refusal. Not fixed here — it is a
different defect in a different function, and bundling it would have made neither individually
auditable.

Gate: `VERIFY OK — 1099 passed, 0 skipped`.
