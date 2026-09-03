# Impact Map: Visual-Variety-Aware Selection (Task T4.6)

## 1. Target Symbols & Callers

### New Symbols in `src/hawedit/pipeline.py`
- `calculate_visual_variety(span: tuple[int, int], shot_cuts_ms: Sequence[int]) -> float`:
  Calculates source cuts per second within the span.
- Exported in `pipeline.py`'s `__all__` or public surface.

### Modified Symbols in `src/hawedit/pipeline.py`
- `build_parser`:
  Add `--visual-variety` boolean flag (default `False`).
- `run_pipeline`:
  Accept `visual_variety: bool = False`.
  In winner selection among shippable candidates:
  Update sort key to incorporate `variety` when `visual_variety` is enabled.
- `main`:
  Forward `args.visual_variety` to `run_pipeline`.

### Modified Test Modules
- `tests/test_pipeline.py`:
  - Unit tests for `calculate_visual_variety`: interior cut counting, edge handling, empty cuts, zero duration.
  - Integration test verifying candidates tying on `hook_score` break in favor of higher visual variety when `visual_variety=True`.
  - Integration test verifying default `visual_variety=False` preserves existing order.
  - CLI argument parsing test for `--visual-variety`.

## 2. Risk Assessment
- **Breaking Changes:** Zero. Default behavior (`visual_variety=False`) produces identical sorting order and identical winners.
- **Dependencies:** Uses existing `IngestResult.shot_cuts_ms` from Stage 0. Zero new external libraries.
