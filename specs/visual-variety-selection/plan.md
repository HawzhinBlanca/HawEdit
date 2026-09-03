# Plan: Visual-Variety-Aware Selection (Task T4.6)

Approved-by: Autonomous Goal Execution (/goal)

## 1. Overview
Implement visual-variety-aware candidate selection behind the `--visual-variety` flag in `src/hawedit/pipeline.py`. When enabled, ties between candidates with equal hook score, payoff strength, and beat ending are broken in favor of footage with more frequent camera angle cuts per second.

## 2. Implementation Steps

### Step 1: Visual Variety Calculation & Tiebreaker Logic (`pipeline.py`)
1. Implement `calculate_visual_variety(span: tuple[int, int], shot_cuts_ms: Sequence[int]) -> float`:
   - Compute `duration_s = (span[1] - span[0]) / 1000.0`.
   - If `duration_s <= 0`: return `0.0`.
   - Count cuts strictly inside the span: `span[0] < cut < span[1]`.
   - Return `cuts / duration_s`.
2. Update `run_pipeline`:
   - Add parameter `visual_variety: bool = False`.
   - Update `_shippable_sort_key` in winner selection:
     Include `calculate_visual_variety(candidate.span, ingested.shot_cuts_ms)` as the tiebreaker when `visual_variety` is enabled.
3. Update `build_parser` and `main`:
   - Add `--visual-variety` flag.
   - Forward `args.visual_variety` in `main`.

### Step 2: Test Suite (`tests/test_pipeline.py`)
1. Add `test_calculate_visual_variety_computes_cuts_per_second`:
   - Checks accurate calculation with multiple cuts, boundary cuts, and zero cuts.
   - Verifies zero duration returns 0.0.
2. Add `test_winner_selection_breaks_ties_on_visual_variety_when_flag_enabled`:
   - Two candidates with identical hook score (0.80), payoff strength (0.70), and ends_on_a_beat (True):
     Candidate A has 0 cuts.
     Candidate B has 3 cuts.
   - With `visual_variety=False`: Candidate A wins (default behavior).
   - With `visual_variety=True`: Candidate B wins (visual variety tiebreak).
3. Add `test_pipeline_visual_variety_argument_is_parsed`:
   - Verifies `--visual-variety` sets `args.visual_variety = True`.

### Step 3: Verification & Cryptographic Ledger
1. Run `verify.sh --fast` for linting and typechecking.
2. Run full `verify.sh` across all tests.
3. Ratchet test floor if required.
4. Record completion via `scripts/update-ledger.sh visual-variety-selection T1 ...` and `T2 ...`.
5. Update `specs/pro-grade-program/tasks.md`.
