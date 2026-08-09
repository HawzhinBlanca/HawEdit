# A nonsense threshold reported 0.0, and §8.2 reads 0.0 as "collapse this path"

> Measured 2026-08-09 on hawapc01 against `ad7b194`.

§8.2's three retrieval metrics take a cutoff `k` and an overlap threshold `iou_match`. Neither was
validated. Both fail the same way: every candidate stops matching, the metric reports **0.0**, and
§8.2's collapse test — *"If Path B never surfaces a winner Path A missed, collapse it"* — reads
that as licence to delete a discovery path.

This is D-077's defect arriving by a second route. That one produced an unmeasured zero from an
empty gold set; this one produces a measured-looking zero from a bad argument.

## Reproduced: one gold winner, retrieved exactly, IoU = 1.0

Perfect overlap. Any honest threshold must find it.

```
  iou_match=0.5    recall=1.0    by_path.verbal=1.0    unique.verbal=1
  iou_match=1.0    recall=1.0    by_path.verbal=1.0    unique.verbal=1
  iou_match=1.5    recall=0.0    by_path.verbal=0.0    unique.verbal=0     <- unreachable
  iou_match=2.0    recall=0.0    by_path.verbal=0.0    unique.verbal=0     <- unreachable
  iou_match=-1.0   recall=1.0    by_path.verbal=1.0    unique.verbal=1     <- matches anything
  iou_match=nan    recall=0.0    by_path.verbal=0.0    unique.verbal=0     <- silently total failure
```

`nan` is the worst of them: NaN comparisons are always false, so `>= iou_match` never holds and
the metric reports complete failure without a hint that the threshold was garbage.

`k` is unvalidated in the same way, and was not in the original finding — found while grepping the
callers:

```
  k=20   recall=1.0
  k=1    recall=1.0
  k=0    recall=0.0     <- Recall@0 is not a question
  k=-5   recall=0.0
```

Fixing `iou_match` alone would have left half the defect in place, so one guard covers both.

## Where the guard goes, and why not in the funnel

`_found_winners` is the shared funnel all three metrics route through, and it is the obvious
place — but it is **skipped when the gold set has no winners**, because each metric short-circuits
to `None`/`{}` first. A caller passing `k=-5` against an unlabelled set would have been handed
"unmeasured" and never told the cutoff was nonsense.

So `_assert_metric_parameters(k, iou_match)` is called at the three public entry points, ahead of
the short-circuit. One rule, three places where the arguments enter — the same shape as D-071's
overwrite guard, and not three copies of a rule.

Verified across every combination:

```
recall_at_k          iou_match=1.5 / nan / -1.0 / k=0 / k=-5    all refused
recall_at_k_by_path  iou_match=1.5 / nan / -1.0 / k=0 / k=-5    all refused
path_unique_wins     iou_match=1.5 / nan / -1.0 / k=0 / k=-5    all refused
```

## Reconciliation correction: zero is not a legal boundary

The first version of this evidence called `0.0` legal and described it as "any overlap counts".
That was wrong for the implemented `temporal_iou >= iou_match` comparison: disjoint spans have IoU
exactly zero, so a zero threshold also counts **no overlap**. Branch reconciliation exposed and
corrected that contradiction. The legal interval is `(0, 1]`; `1.0` remains the exact-span control.

The reconciled validation also refuses boolean/string thresholds and boolean/fractional K values,
and applies the shared threshold rule to Stage 3 merge before an empty-input return. The stricter
mutation audit is recorded in `evidence/iou-threshold-validation.md`: bypassing merge validation,
admitting zero, and bypassing one metric's K validation were each caught (3/3). The earlier 7/7
figure must not be quoted as evidence for the corrected contract because one of its expectations
was precisely the invalid zero boundary.

The complete gate is rerun after reconciliation; its settled count belongs in the current audit
report rather than this historical measurement file.
