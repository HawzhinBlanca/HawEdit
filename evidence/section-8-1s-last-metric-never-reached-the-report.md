# Section 8.1 alignment never reached the report

Measured 2026-08-09 against upstream `06adf58`; integrated into the readiness branch as D-161.

Before this change, `_score_item` populated `ItemScore.alignment`, but the written model report had
no alignment key. Six timed items shifted by 30 ms each carried matched 2/2 words, 30 ms onset and
offset error, a 1.0 within-50-ms rate, and full coverage; none of those facts appeared in JSON.

The report now emits an aggregate containing:

- matched and reference word totals plus coverage;
- matched-word-weighted mean onset and offset absolute errors;
- matched-word-weighted within-tolerance rate and its exact tolerance;
- the number of items that contributed timing evidence.

Matched-word weighting prevents a two-word item from outweighing a sixty-word item. Coverage travels
with the errors so good timing on a tiny transcribed subset cannot read as good alignment overall.
No evidence is `null`, never a perfect zero, and mixed tolerances are refused.

Regression controls cover a 30 ms in-threshold shift, a 120 ms out-of-threshold shift, six-item
coverage, the ordinary unmeasured case, and mixed 50/200 ms thresholds. The recorded report schema
also requires the alignment key, preventing a future silent drop.
