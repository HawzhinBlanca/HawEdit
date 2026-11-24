# Spec — C5 Pairwise ranking replacing asserted weights (`c5-pairwise-ranking`)

EARS criteria. Each names the automated test(s) that verify it in `tests/test_judge_calibration.py` (and `tests/test_pipeline.py` / `tests/test_episode.py` for callers).

- **AC1** WHEN `src/hawedit/judge.py` ranks verdicts, THE system SHALL NOT compute the retired `0.40/0.30/0.20/0.10` weighted sum (`tournament_score`), and SHALL reject any prompt or schema containing `"virality"` / virality-score prediction.
  `test_asserted_weights_retired_and_no_virality_score_emitted`
- **AC2** WHEN two candidates are compared by `GeminiPairwiseJudge`, THE request SHALL present both Kurdish candidates, ask which one a Kurdish viewer would keep watching, enforce `PAIRWISE_SCHEMA` (`winner` in `{"A", "B", "TIE"}`, non-empty Sorani `reason_ckb` via `_kurdish_field`), check §7 routability (`NotRoutable`), and refuse malformed or non-Kurdish answers (`JudgeUnusable` / `ValueError`).
  `test_pairwise_judge_schema_sorani_reason_and_refusals`
- **AC3** WHEN `pairwise_rank_verdicts` receives a mix of eligible and ineligible verdicts (`meaning_fidelity < 0.70`, `misleading_edit_risk > 0.10`, or `self_contained == False`), THE system SHALL exclude all ineligible verdicts BEFORE scheduling any pairwise comparisons so high hook score can never promote an ineligible clip.
  `test_pairwise_ranking_filters_ineligible_before_bouts`
- **AC4** WHEN `M` eligible verdicts (`2 <= M <= 12`, capped from >12 deterministically) enter pairwise ranking over 2–3 Swiss rounds, THE ranker SHALL aggregate outcomes via `hawedit.repurposing.pairwise_preference` (win=1.0, tie=0.5, loss=0.0 normalized by appearances) plus opponent-strength tiebreak, alternating/swapping A/B order across rounds to mitigate position bias.
  `test_swiss_tournament_ranks_top_candidates_via_pairwise_win_rate`
- **AC5** WHEN `<= 1` eligible verdict is present, THE pairwise ranker SHALL issue zero comparator calls; when `comparator` fails during `run_pipeline` Stage 4 pairwise ranking, THE pipeline SHALL fail/report Stage 4 operationally instead of silently falling back to hardcoded weights.
  `test_pairwise_ranker_skips_llm_for_single_verdict_and_fails_loudly_on_error`
- **AC6** WHEN `run_pipeline` (Stage 4 selection at `pipeline.py:3686`) and `plan_episode` (`episode.py:340`) rank `>= 2` shippable verdicts with a pairwise comparator or `GeminiJudge`, both single-clip selection and multi-clip episode planning SHALL agree on top-candidate ranking order while preserving `EpisodePlanConfig` separation and lexical diversity constraints.
  `test_single_and_episode_modes_share_pairwise_ranking_and_eligibility`
