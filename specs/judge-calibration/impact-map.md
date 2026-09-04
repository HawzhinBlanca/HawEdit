# Impact Map — Judge Calibration (Task T4.3)

## 1. Symbols Modified / Created
- `hawedit.gemini._PROMPT_TEMPLATE`:
  - Contains rubric anchors for Sorani hook scoring.
- `hawedit.clip`:
  - `MIN_MEANING_FIDELITY: Final = 0.70`
  - `MIN_CULTURAL_LANDING: Final = 0.70`
  - `Clip.assert_renderable()`: Gates both metrics.
- `hawedit.judge`:
  - `tournament_rank_verdicts`: Ranks multiple passing candidates.
  - `compute_repeat_k_agreement`: Quantifies scoring variance across runs.
- `hawedit.pipeline`:
  - Uses tournament ranking when selecting among passing candidates.

## 2. Test Plan
- `tests/test_judge_calibration.py`:
  - `test_prompt_template_contains_calibrated_sorani_rubric_anchors`
  - `test_clip_assert_renderable_gates_meaning_fidelity`
  - `test_clip_assert_renderable_gates_cultural_landing`
  - `test_tournament_rank_verdicts_ranks_by_multidimensional_quality`
  - `test_compute_repeat_k_agreement_calculates_metric_concordance`
