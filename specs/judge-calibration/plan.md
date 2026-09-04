# Plan — Judge Calibration (Task T4.3)

## 1. Goal
Calibrate the Stage 4 Kurdish editorial judge through:
1. Grounded Sorani rubric anchors in the prompt template.
2. Calibrated tournament ranking across passing candidates instead of naive `max(hook_score)`.
3. Gating `meaning_fidelity` ($\ge 0.70$) and `cultural_landing` ($\ge 0.70$) in `Clip.assert_renderable()`.
4. Measuring Repeat-K ($K=3$) scoring agreement / variance.
5. Re-affirming `MAX_MISLEADING_EDIT_RISK = 0.10` empirical floor.

## 2. Proposed Changes

### `src/hawedit/gemini.py`
- Update `_PROMPT_TEMPLATE` with explicit Sorani rubric anchors for hook evaluation (0.2, 0.5, 0.8+).

### `src/hawedit/clip.py`
- Define `MIN_MEANING_FIDELITY: Final = 0.70` and `MIN_CULTURAL_LANDING: Final = 0.70`.
- In `Clip.assert_renderable()`:
  - Add explicit checks raising `EditorialBelowThreshold` if `meaning_fidelity < MIN_MEANING_FIDELITY` or `cultural_landing < MIN_CULTURAL_LANDING`.

### `src/hawedit/judge.py`
- Add `tournament_rank_verdicts(verdicts: Sequence[JudgeVerdict]) -> list[tuple[JudgeVerdict, float]]`:
  Computes multi-dimensional tournament score:
  $0.40 \cdot \text{hook\_score} + 0.30 \cdot \text{payoff\_strength} + 0.20 \cdot \text{meaning\_fidelity} + 0.10 \cdot \text{cultural\_landing}$.
- Add `compute_repeat_k_agreement(verdicts: Sequence[JudgeVerdict]) -> dict[str, float]`:
  Computes mean and variance across repeat judge evaluations.

### `src/hawedit/pipeline.py`
- Update winner selection in `_automatic_sentence_selection` to break ties and rank passers using `tournament_rank_verdicts`.

## 3. Verification Plan
- Unit tests in `tests/test_judge_calibration.py`:
  - `test_prompt_template_contains_calibrated_sorani_rubric_anchors`
  - `test_clip_assert_renderable_gates_meaning_fidelity`
  - `test_clip_assert_renderable_gates_cultural_landing`
  - `test_tournament_rank_verdicts_ranks_by_multidimensional_quality`
  - `test_compute_repeat_k_agreement_calculates_metric_concordance`
- Run `verify.sh` and update ledger.

Approved-by: Hawa
