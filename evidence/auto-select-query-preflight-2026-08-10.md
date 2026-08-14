# Auto-selection requires a query-capable discovery path

> Integrated 2026-08-10 from protected-main finding `e2c768f`; readiness fix
> `7f97ce7`. This evidence distinguishes the measured upstream defect from the stricter
> preflight that was already present on the readiness branch.

## What protected main measured

Protected main accepted `--visual --auto-select` without either `--visual-query` or Path A. On the
real 2,313.8-second Sorani episode it spent about 170 seconds, including about 111 seconds in
Stage 0, before Stage 2 reported that it had no retrieval query. It produced 164 planned windows,
zero candidates and no selection. The visual checkpoints were installed but were never loaded;
the wasted work was media analysis, not GPU inference.

The corresponding fixture control separated the missing-query path from a working query path:
the no-query run stopped after about 3.5 seconds, while an explicit Sorani query ran retrieval and
stopped later, after about 14 seconds, for a media-specific reason. Protected main recorded that
measurement in `evidence/auto-select-accepted-a-path-that-could-not-produce.md`.

## Readiness-tree classification

The readiness parent `e89f8d9` could not reproduce that exact expensive path. Its earlier CLI
contract already refused `--visual` without either `--visual-query` or Path A before Stage 0:

```python
if args.visual and not (args.visual_query or args.gemini or args.vertex_project):
    raise ValueError("--visual without Path A requires --visual-query")
```

That is semantic supersession, not permission to ignore the upstream finding. The adjacent
`--auto-select` guard still described mere flag presence as a producer, and the generic Stage 3
skip still told operators that `--visual` alone enabled composed Path B. Those representations
could drift away from the stronger earlier contract.

## Integrated rule

`_run_from_args` now names the capability directly:

```python
stage_3_can_produce = bool(args.gemini or args.vertex_project) or bool(
    args.visual and visual_query
)
```

Therefore Path A is query-capable on its own, while Path B is query-capable only when visual
retrieval is enabled and the normalized explicit query is nonempty. The whole transcript remains
the corpus, never a fallback query. `_STAGE_3_DISCOVERY` gives the same instruction.

Seven behavioral tests hold both sides of the boundary:

- visual auto-selection without a query refuses before the work directory exists;
- visual auto-selection with a Sorani query passes this preflight;
- Path A passes without an explicit visual query;
- no discovery path refuses;
- `--visual-query` without `--visual` is still rejected by the earlier contract;
- whitespace-only queries refuse before Stage 0; and
- the structured skip names `--visual-query`.

Focused acceptance: `tests/test_pipeline.py` passed 125/125 with Ruff, formatting and mypy clean.
The canonical whole-repository gate is recorded separately after the history join.

## Why protected main is not copied wholesale

The other protected-main delta, `9e8f128`, repaired interrupted delivery in its older flat-file
publisher. Readiness already publishes the five-file delivery as one hidden private
`ArtifactBundle` directory, validates the exact set, and performs a single no-replace directory
rename. `test_a_crashed_private_bundle_does_not_block_a_clean_retry` proves that an abandoned
private bundle remains invisible and does not wedge a retry; concurrent publication is separately
covered. A hard kill may leave the hidden private directory for explicit cleanup, but it cannot
expose a partial delivery or block a clean retry. Copying the older flat-file recovery path would
weaken that ownership model.
