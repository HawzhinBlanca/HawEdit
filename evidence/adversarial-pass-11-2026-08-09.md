# Adversarial pass #11 — the dual-path merge

> Run 2026-08-09 on hawapc01 against `7fd5a55`.
> Target: **M2.5**, DONE — §3 Stage 3's "union, never intersect", never attacked.

§3, about this exact function: **"This is the most important structural decision in the system."**
§8.2 spends its output on `recall_at_k_by_path` and `path_unique_wins` — the numbers that decide
whether Path B earns its cost. Fourteen DONE rows had never had a pass; this is the second.

M6.2 was the first choice and was set aside on inspection: its cell says "Delivered in M2.2", and
M2.2 has already been audited (D-078's 78,125-combination sweep). Attacking it would have re-run
someone else's pass.

## What held

```
CAUGHT  Path B's unmatched candidates dropped (intersect, not union)
CAUGHT  the merged span becomes the union, not the anchor's
CAUGHT  one visual candidate corroborates every overlapping verbal one
CAUGHT  a path dedupes itself: verbal candidates can claim each other
CAUGHT  candidates from different media can merge
CAUGHT  an unmeasured visual score becomes 0.0 instead of None
CAUGHT  the visual path's SV6D is dropped on the merged candidate
```

## What did not

**Rank versus id.** The existing test asserts *"the lower-ranked verbal candidate should claim it"*
— and its fixture is `v1` rank 1, `v2` rank 2, so id order and rank order agree and the assertion
holds either way:

```
sorted(verbal, key=lambda c: (c.rank, c.candidate_id))  ->  v1 claims x1
sorted(verbal, key=lambda c: c.candidate_id)            ->  v1 claims x1   (suite still green)
```

The replacement makes them disagree — `v2` at rank 1, `v1` at rank 2 — so only rank order gives
`v2`. Which moment gets the corroboration is what `path_unique_wins` counts.

**The promised output order.** The docstring promises "(media, then start, then id)". The
determinism test shuffles inputs 20 times and compares against a reference, but every visual in its
fixture is claimed, so there are no leftovers and the merge's internal order — anchors in rank order
— is already stable. Deleting the final sort changed nothing it could see. The new test gives Path B
a candidate that *starts first*:

```
verbal v1 10_000..14_000        leftovers are appended after the anchors, so
visual x1      0.. 4_000        without the sort the output is [v1, x1]
contract                        [x1, v1] — earlier start, earlier in the list
```

**Which rank §8.2 scores against.** `to_retrieved` takes `min` of the two ranks and says why: *"a
moment Path B ranked 2nd was available at position 2 whatever Path A thought of it."* `max` survived,
because the only test exercising it scores at `k=20` where 2 and 9 are the same answer. Pinned now at
verbal 9 / visual 2 → **rank 2**, with a control at verbal 2 / visual 7 — returning `verbal_rank`
whenever it exists satisfies the first case by accident of which number is smaller.

## After

```
10/10
```

One mutation had to be rewritten to count at all: deleting `del unclaimed[…]` emptied its `if` block,
the module stopped importing, and the audit reported SKIPPED rather than a false CAUGHT. As `pass`, it
is caught.

**No production code changed.** All three survivors were tests that could not discriminate — the
merge does claim in rank order, does sort its output, and does take the better rank. The row was
true and three of its claims were unheld, which is the difference this pass exists to find.

Gate: `VERIFY OK — 1286 passed, 0 skipped`.
