# Plan — C5 Pairwise ranking replacing asserted weights

Read `research.md` first.

## Approach

Retire the asserted `0.40 * hook_score + 0.30 * payoff_strength + 0.20 * meaning_fidelity + 0.10 * cultural_landing` formula in `src/hawedit/judge.py:799-818` and replace it with a bounded 2–3 round Swiss pairwise tournament asking which candidate a Kurdish viewer would keep watching:

1. **Pairwise judge contract & Swiss tournament (`src/hawedit/judge.py`):**
   - Add `PAIRWISE_SCHEMA` (`winner: enum["A", "B", "TIE"]`, `reason_ckb: str`), `PairwiseMatch` frozen dataclass (enforcing `_kurdish_field(reason_ckb, "reason_ckb")` and distinct candidate IDs), `PairwiseComparator` Protocol, and `GeminiPairwiseJudge` wrapping `GeminiJudge` / `VertexGeminiJudge` (`route()` / `NotRoutable` + `generate_json` + token ceiling check + `BilledCall` tracking; asks *"which of these two would a Kurdish viewer keep watching"* with zero `"virality score"`).
   - Remove `0.40/0.30/0.20/0.10` (`tournament_score` retired cleanly; replaced by `pairwise_rank_verdicts` + Swiss pairing engine, max `12` eligible candidates, default `3` rounds, `2–3` allowed; position-alternating `(A, B)` / `(B, A)` scheduling across rounds; scored via `hawedit.repurposing.pairwise_preference` win-rate + opponent-strength Buchholz sum).
   - Hard eligibility (`meaning_fidelity >= 0.70`, `misleading_edit_risk <= 0.10`, `self_contained`) runs BEFORE any pairwise bout, preserving `test_story.py:858-891` and `test_judge_calibration.py:279`.
   - For `tournament_rank_verdicts` compatibility (callers without a live Gemini client in offline unit tests / direct-verdict calls), accept optional `comparator: PairwiseComparator | None = None`: if `len <= 1`, return immediately with `0` comparisons; if `comparator` is given, run the Swiss tournament; if `comparator is None` (explicitly uncompared offline pool), order deterministically by unweighted lexicographic tiebreak `(verdict.hook_score, verdict.meaning_fidelity, verdict.cultural_landing, verdict.candidate_id)` without asserted weights — while `run_pipeline` when `judge is not None` ALWAYS constructs `GeminiPairwiseJudge(judge)` for `len(shippable) >= 2` and fails visibly if comparison fails (no silent fallback to weights!).
2. **Wire Stage 4 & Episode Planning (`src/hawedit/pipeline.py`, `src/hawedit/episode.py`):**
   - Update `pipeline.py:3686` (`_shippable_sort_key` / winner selection): when `len(shippable) >= 2` and `judge is not None` (or injected `pairwise_comparator`), run `GeminiPairwiseJudge(judge)` over top `<= 12` shippable verdicts (`_shippable` pre-capped deterministically if `> 12`), log `BilledCall`s under `stage="pairwise_rank"`, pick winner from tournament rank #1 (using `calculate_visual_variety` only as exact same-win-rate tiebreak if enabled). Refuses / surfaces `StageSkipped` operational error if the pairwise call fails (`GeminiUnavailable`, `JudgeUnusable`, `NotRoutable`, `RequestTooLarge`).
   - Update `episode.py:22, 340` (`plan_episode`, `select_episode_plan`): replace `tournament_score` call with optional `pairwise_comparator` + `pairwise_rank_verdicts` pre-ranking while preserving separation, overlap, and lexical diversity filters (`tests/test_episode.py`).
3. **Update affected calibration tests (`tests/test_judge_calibration.py`, `tests/test_story.py`):**
   - Replace assertions referencing `tournament_score(v2) > tournament_score(v1)` weights (`test_judge_calibration.py:171-195`) with deterministic pairwise Swiss ranking tests proving eligibility-first filtering, A/B win-rate ranking, position bias mitigation, zero `"virality score"`, and single/episode concordance (`AC1–AC6`).

No new third-party dependencies.

## Files and symbols

| File | Symbol | Change |
|---|---|---|
| `src/hawedit/judge.py` | `tournament_score` (`:799-818`), `tournament_rank_verdicts` (`:821-859`), new `PAIRWISE_SCHEMA`, `PairwiseMatch`, `PairwiseComparator`, `GeminiPairwiseJudge`, `pairwise_rank_verdicts` | Remove `0.40/0.30/0.20/0.10` linear weights; add Swiss 2–3 round pairwise ranking (`<= 12` eligible candidates) backed by `repurposing.pairwise_preference` |
| `src/hawedit/pipeline.py` | `_shippable_sort_key` / Stage 4 winner selection (`:168`, `:3620-3695`), `run_pipeline` | Replace `tournament_score(verd)` with `GeminiPairwiseJudge` pairwise tournament when `>= 2` shippable candidates exist; record `BilledCall`s and fail visibly on judge error |
| `src/hawedit/episode.py` | `plan_episode` (`:22, 272, 335-347`), `select_episode_plan` (`:477`) | Accept optional `comparator`, replace `tournament_score(verdict)` with pairwise ranking before diversity/separation filtering |
| `tests/test_judge_calibration.py` | `:28-29, 171-195, 279-297` | Replace asserted-weight `tournament_score` checks with AC1–AC6 pairwise ranking and calibration alignment tests |
| `tests/test_story.py`, `tests/test_episode.py`, `tests/test_pipeline.py` | `:19, 858, 891` (`test_story.py`), integration checks | Verify callers keep eligibility-first behavior and pass `AC6` |
| `DECISIONS.md` | New `D-346` | Record retirement of `0.40/0.30/0.20/0.10` weights and Swiss pairwise ranking contract |

## Divergence and ADR

- Implements `specs/pro-grade-program/gemini-task-sheet-2026-11-18.md` §3 C5 cleanly within `BLUEPRINT.md` §3 Stage 4 / §8.2 (`repurposing.pairwise_preference`). Records ADR `D-346` (assigned Lane 3 range `D-344..D-347`).

## Risks & cross-lane notes

- **Sibling heuristic weights outside `judge.py:799-816`:** `screener.py:167` (`0.50/0.35/0.15`), `story.py:981` (`0.50/0.50`), and `condenser.py:835, 958` (`0.40/0.30/0.30`) also contain linear weights. Plan scopes C5 specifically to `judge.py:799-816` (`tournament_score` / Stage 4 & `episode.py`), leaving `screener.py` (pre-filter heuristics) and `story.py`/`condenser.py` intact unless owner asks to replace `screener.py` weights too (`[HAWA]` question flagged).
- **Gemini model & billing in Stage 4:** `GeminiPairwiseJudge` reuses `GeminiJudge` (`gemini-2.5-pro` or Lane 1's upgraded A5 judge model once landed), staying safely within A5's judge wrapper (`count_parts`, `assert_within_tier`, `BilledCall`) without hardcoding a retired model ID.
- **VEX source digest pin (`security/wsl-asr-vex.json`):** Editing `judge.py`, `episode.py`, and `pipeline.py` shifts `package_digest(src/hawedit)` (`tests/test_vex.py:140-163`), requiring A3 parking or owner re-pin on Round 2 merge.

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"
