# Tasks ledger — c5-pairwise-ranking
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  Add `PAIRWISE_SCHEMA`, `PairwiseMatch`, `PairwiseComparator`, and `GeminiPairwiseJudge` in `src/hawedit/judge.py` asking which candidate a Kurdish viewer would keep watching (zero virality score; Sorani reason + NotRoutable guards)   (tests: test_asserted_weights_retired_and_no_virality_score_emitted, test_pairwise_judge_schema_sorani_reason_and_refusals)
- [x] T2  Retire `0.40/0.30/0.20/0.10` in `judge.py:799-818`; implement bounded (`<= 12` eligible, 2–3 Swiss rounds, A/B alternation) `pairwise_rank_verdicts` backed by `repurposing.pairwise_preference`, filtering ineligible verdicts before bouts   (tests: test_pairwise_ranking_filters_ineligible_before_bouts, test_swiss_tournament_ranks_top_candidates_via_pairwise_win_rate, test_pairwise_ranker_skips_llm_for_single_verdict_and_fails_loudly_on_error)
- [x] T3  Wire `pairwise_rank_verdicts` / `GeminiPairwiseJudge` into `pipeline.py:3686` and `episode.py:340`, update `tests/test_judge_calibration.py`, and record ADR `D-346`   (tests: test_single_and_episode_modes_share_pairwise_ranking_and_eligibility)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
