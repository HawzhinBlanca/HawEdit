# Impact Map — Length Variants 15/30/60 (Task T2.11)

## 1. Symbols Modified / Created
- `hawedit.variants`: New module
  - `LengthVariant`: Dataclass carrying variant metadata, span, and complete sentences.
  - `plan_length_variants`: Function partitioning sentences into optimal target duration sub-spans.
- `hawedit.clip.Output`:
  - `durations: tuple[int, ...]`: Already exists, will receive populated multi-duration tuples.
- `hawedit.pipeline`:
  - Optionally emits sibling variant bundles when multiple durations are planned.

## 2. Test Plan
- `tests/test_variants.py`:
  - `test_plan_length_variants_enforces_sentence_completeness`
  - `test_plan_length_variants_anchors_on_hook_sentence`
  - `test_plan_length_variants_selects_optimal_sub_spans_for_targets`
  - `test_plan_length_variants_handles_short_clips_gracefully`
  - `test_length_variant_serializes_and_roundtrips`
