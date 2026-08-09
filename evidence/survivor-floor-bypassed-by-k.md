# The survivor floor was checked against the index, so `k` walked past it

> Measured 2026-08-09 on hawapc01 against `b34d88d`, against a green 1,142 baseline.

D-037 clause 4 fixes Stage 2's behaviour: below the survivor floor, retrieval **refuses** rather
than shortening the slice. D-066 restored that guarantee after it was once reverted to
`min(keep, len(reranked))`. The check looked only at `len(index)`.

## Measured on a 60-window index, keep=5

```
  k=50 -> 5 survivors, ranks [1,2,3,4,5]
  k=5  -> 5 survivors, ranks [1,2,3,4,5]
  k=3  -> 3 survivors, ranks [1,2,3]        <- no error
  k=1  -> 1 survivor
  k=0  -> 0 survivors, empty tuple
  k=-5 -> 5 survivors, after reranking 55 windows
```

Three survivors in a slice that says five is precisely the number D-037 clause 4 refuses to produce,
because §8.2 counts Recall@K on this list.

The negative case is a second, smaller defect. `retrieve` slices `scored[:k]`, so a negative `k`
drops the **tail** instead of keeping a head: 55 windows reranked where 5 were asked for — silently
different semantics, and on a real index that is GPU time spent on windows nobody wanted.

## The fix is arithmetic, not a threshold

Retrieving fewer candidates than the survivor count cannot produce `keep` survivors. The slice could
only ever be short, which is the thing clause 4 forbids. So `k < keep` is refused — and that single
relation covers `k=3`, `k=1`, `k=0` and every negative value at once. Nothing is chosen; the two
arguments settle it between them. That is what makes this a fix rather than a third `BLOCKED` entry
alongside #14 and #15, both of which are genuinely unset thresholds.

```
  k=50 -> 5 survivors          k=3  -> refused: k=3 retrieves fewer candidates than the 5 …
  k=5  -> 5 survivors          k=1  -> refused
                               k=0  -> refused
                               k=-5 -> refused
```

**Placed in `rerank_and_keep`, not `retrieve`.** `retrieve`'s contract is "the top k" and that is
honest at any k; the survivor floor is Stage 2's concern, and `rerank_and_keep` is the only function
holding both numbers. One guard, where the relation is visible.

## Mutation audit, against a baseline verified green first

```
baseline FAILED=0
CAUGHT   the k guard never fires
CAUGHT   only negative k is refused, k=3 slips through
CAUGHT   k == keep is wrongly refused (the boundary)

3/3
```

The third is the control doing the work. `k == keep` can still fill the slice exactly, so refusing it
would be a new defect wearing the fix's clothes — and no refusal test could see that. This is the
third consecutive iteration where the over-strict direction was catchable only by a control
(D-088's length-plus-moment label, D-087's ordinary ASS, and now the tight `k` boundary).

## Scope, stated plainly

`pipeline.py` constructs `VisualComposer` without `retrieve_k`, so the shipped CLI always ran at §3's
depth of 50 and could not reach this. **The defect was in the public API and in the written proof**:
D-037 clause 4's guarantee was weaker than its own wording, and a caller using the documented
composer entry point could obtain a three-survivor Stage 2 result from a module whose docstring says
short media is "refused explicitly rather than mislabeled as a top-5 result".

Gate: `VERIFY OK — 1148 passed, 0 skipped`.
