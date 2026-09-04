# Plan — Length Variants 15/30/60 (§5 durations) (Task T2.11)

## 1. Goal
Implement sentence-complete length variant planning and deliverable bundle emission for target durations 15s, 30s, and 60s inside winning clips, satisfying BLUEPRINT.md §5 `durations` contract and pro-grade multi-platform requirements.

## 2. Proposed Changes

### Module `src/hawedit/variants.py`
1. `LengthVariant`:
   ```python
   @dataclass(frozen=True, slots=True)
   class LengthVariant:
       target_s: int
       label: str
       in_ms: int
       out_ms: int
       duration_ms: int
       sentence_indices: tuple[int, ...]
       sentences: tuple[Sentence, ...]
   ```
2. `plan_length_variants`:
   - Inputs: `sentences: Sequence[Sentence]`, `targets_s: Sequence[int] = (15, 30, 60)`, `min_ratio: float = 0.65`, `max_ratio: float = 1.35`.
   - Invariants:
     - All sentences in the sub-span must have `complete == True`.
     - Preserves the hook: short variants (15s and 30s) anchor on sentence 0.
     - For each target duration $T \in (15, 30, 60)$:
       - Search for the contiguous sentence prefix/sub-span `sentences[0:k]` whose duration $\in [T \times 1000 \times \text{min\_ratio}, T \times 1000 \times \text{max\_ratio}]$ that minimizes $| \text{duration} - T \times 1000 |$.
       - Avoid duplicate identical spans across targets.
       - Returns a tuple of non-empty `LengthVariant` instances sorted by duration.

### Integration in `src/hawedit/delivery.py` & `src/hawedit/pipeline.py`
1. When length variants are requested or planned:
   - Construct sub-span `Clip` copies with adjusted boundaries and timestamps.
   - Update `Output.durations` on the primary clip to list the durations of all available variants.

## 3. Verification Plan
- Unit tests in `tests/test_variants.py`:
  - `test_plan_length_variants_enforces_sentence_completeness`
  - `test_plan_length_variants_anchors_on_hook_sentence`
  - `test_plan_length_variants_selects_optimal_sub_spans_for_targets`
  - `test_plan_length_variants_handles_short_clips_gracefully`
  - `test_length_variant_serializes_and_roundtrips`
- End-to-end multi reality check on real media (`work/ep29-VbX8UWwl1c4-s25-25`).

Approved-by: Hawa
