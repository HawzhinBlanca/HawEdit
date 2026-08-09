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

## The legal boundaries are controls, not oversights

`0.0` and `1.0` are both accepted. `0.0` means "any overlap counts" and `1.0` means "the exact
span only"; §8.2 forbids neither, and a guard that rejected them would break honest callers while
still passing every refusal test above. `test_the_legal_threshold_boundaries_are_still_accepted`
requires the perfect match to be found at `0.0`, `0.5`, `DEFAULT_IOU_MATCH` and `1.0`, and
`test_a_cutoff_of_one_is_still_accepted` pins that Recall@1 is a real question.

## Mutation audit, against a baseline verified green first

```
baseline: GREEN
CAUGHT   the iou_match range check is removed
CAUGHT   the k cutoff check is removed
CAUGHT   the upper bound on iou_match is dropped (1.5 accepted)
CAUGHT   the lower bound on iou_match is dropped (-1 accepted)
CAUGHT   k < 1 becomes k < 0, so k=0 slips through
CAUGHT   the legal boundary 1.0 is wrongly rejected
CAUGHT   recall_at_k stops validating

7/7
```

The last two are the ones worth having. *"the legal boundary 1.0 is wrongly rejected"* is caught by
the control rather than by a refusal test — it is the mutation that a suite of refusal tests alone
would wave through. And *"recall_at_k stops validating"* confirms the entry-point placement is
load-bearing: dropping the call from one metric while leaving it in the others is caught.

Run over `tests/test_discovery.py` as well as `tests/test_repurposing.py`, since the former also
calls these metrics.

Gate: `VERIFY OK — 1118 passed, 0 skipped`.
