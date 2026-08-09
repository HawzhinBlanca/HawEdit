# IoU and Recall@K configuration validation · 2026-08-09

## Defect reproduced

The Stage 3 merge and §8.2 recall metrics accepted any runtime value as `iou_match`:

- `-1` and `0` let disjoint spans match because temporal IoU is non-negative;
- `1.5`, positive infinity and NaN prevented every match;
- negative infinity again let every same-media span match; and
- an empty merge or gold set returned normally before exposing the invalid configuration.

The recall metrics also accepted `k=0`, negative, boolean and fractional values. Those inputs
returned plausible zero/unmeasured numbers even though “top K” was not defined.

## Contract implemented

`src/hawedit/repurposing.py` owns one threshold validator used by all three recall surfaces and
`src/hawedit/discovery.py`. It requires a finite, non-boolean numeric value in `(0, 1]`.
Recall additionally requires a positive, non-boolean integer K. Both checks run before an empty
input can return `None`, `{}`, or `()`.

## Focused verification

```text
pytest -q tests/test_repurposing.py tests/test_discovery.py
82 passed
ruff check: passed
ruff format --check: passed
mypy --strict: passed
```

The parameterized regressions exercise eight bad threshold forms at the metric and merge
boundaries and four bad K forms across all three recall metrics.

The complete project gate then reported `1,169 collected, 1,169 passed, 0 skipped`, with Ruff,
format checking and strict mypy clean. `scripts/test-count.floor` ratcheted to 1,169.

Mutation audit, **3/3 caught**:

1. bypass threshold validation in `merge_candidates` — 8/8 threshold cases fail;
2. change `(0, 1]` to `[0, 1]` — the zero case fails; and
3. bypass K validation in `recall_at_k` — 4/4 K cases fail.

## Boundary

This validates metric configuration; it does not choose or tune the threshold. The default
remains D-020's `0.5`, and M7.3 still requires the real labelled editorial set before tuning.
