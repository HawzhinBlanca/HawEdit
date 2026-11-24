# Research — C5 Pairwise ranking replacing asserted weights (`c5-pairwise-ranking`)

Date: 2026-11-18. Worktree: `HawEdit-lane-3` (`gemini/lane-3`, commit `1714a8b`). Host: `HAWAPC01` (`Windows-11-10.0.26300-SP0`), `.venv` Python `3.12.10`. Serena MCP was unavailable in this session's toolset, so all definitions and callers were mapped with `rg -n` over `src/` and `tests/`.

## Problem Today

`src/hawedit/judge.py:799-818` currently scores and ranks judged candidates with an asserted linear formula:

```python
def tournament_score(verdict: JudgeVerdict) -> float:
    base = (
        0.40 * verdict.hook_score
        + 0.30 * getattr(verdict, "payoff_strength", 0.5)
        + 0.20 * verdict.meaning_fidelity
        + 0.10 * verdict.cultural_landing
    )
    risk_penalty = verdict.misleading_edit_risk * 0.20
    beat_bonus = 0.05 if getattr(verdict, "ends_on_a_beat", False) else 0.0
    return round(base - risk_penalty + beat_bonus, 4)
```

Architectural defects (per `specs/pro-grade-program/research.md` §5, `specs/pro-grade-program/gemini-task-sheet-2026-11-18.md` §3 C5, and `DECISIONS.md` / `PROGRESS.md`):
1. **Unmeasured weights.** The `0.40 / 0.30 / 0.20 / 0.10` weights, `-0.20 * misleading_edit_risk`, and `+0.05` beat bonus have never been fitted or verified against human-labelled Kurdish reels (`M7.2` / `M7.3` are unstarted). Linear combination of absolute LLM sub-scores suffers from per-clip calibration drift across episodes.
2. **Research ceiling on absolute scoring.** Predicting absolute engagement / "virality score" in-domain hits ~0.71 rank correlation ceiling and misleads downstream callers into treating LLM point estimates as calibrated cardinals. Pointwise scores can still check *threshold pass/fail* (§2 editorial floor), while **ordering among passing candidates** is significantly sharper via forced-choice A/B comparison.
3. **Hard eligibility must remain decoupled and non-negotiable.** `tournament_rank_verdicts` (`judge.py:841-846`), `_verdict_is_shippable` (`pipeline.py:1386-1400`), and `plan_episode` (`episode.py:298-303`) enforce `BLUEPRINT.md` §2 hard floors (`meaning_fidelity >= 0.70`, `misleading_edit_risk <= 0.10`, `self_contained == True`, plus `_verdict_is_shippable` `hook_score >= 0.75` and `cultural_landing >= 0.70`). No pairwise win may override an eligibility failure.

## Existing Interfaces & Reusable Code

- **`hawedit.repurposing.pairwise_preference`** (`repurposing.py:268-295`) ALREADY implements exact win-rate aggregation `(system_a, system_b, winner)` with `win = 1.0`, `tie (None) = 0.5`, `loss = 0.0`, normalized by appearances (`wins / appearances`), raising `ValueError` on unknown winners. C5 reuses `pairwise_preference` directly instead of duplicating win-rate arithmetic!
- **`hawedit.judge`**:
  - `JudgeVerdict` (`judge.py:203-230`): carries `candidate_id`, `hook_score`, `self_contained`, `meaning_fidelity`, `misleading_edit_risk`, `cultural_landing`, `hook_type`, `payoff_strength`, `ends_on_a_beat`, `title_ckb`, `reason_ckb`, `clip_in_ms`, `clip_out_ms`.
  - `_kurdish_field` (`judge.py:177-199`): enforces Sorani script & §4.1 normalization on Kurdish output text.
  - `_is_verdict_eligible(verdict)` helper can unify hard eligibility checks across `tournament_rank_verdicts` and pairwise pre-filtering (`meaning_fidelity >= 0.70`, `misleading_edit_risk <= 0.10`, `self_contained`).
- **Callers of `tournament_score` & `tournament_rank_verdicts`:**
  - `src/hawedit/judge.py:821-859`: `tournament_rank_verdicts`
  - `src/hawedit/pipeline.py:168, 3686`: `_shippable_sort_key` inside `run_pipeline` Stage 4 (`max(shippable, key=_shippable_sort_key)` when `judge_plans` produces `>= 2` shippable verdicts).
  - `src/hawedit/episode.py:22, 340`: `_rank_key` inside `plan_episode` (also invoked by `select_episode_plan` at `episode.py:500` and `_run_episode_delivery` at `pipeline.py:2646`).
  - `tests/test_judge_calibration.py:28-29, 171-195, 279-288`, `tests/test_story.py:19, 858, 891`.
- **Related sibling weighted scorers found by grep (`0\.[0-9]+ \*`):**
  - `src/hawedit/screener.py:167` (`calculate_screener_score`: `0.50 * hook + 0.35 * payoff + 0.15 * (1 - risk)`) — pre-Stage 4 heuristic screener funnel (`D-275`). Out of `judge.py:799-816` scope unless owner confirms retirement in `[HAWA]` follow-up.
  - `src/hawedit/story.py:981` (`rank_editorial_proposals`: `0.50 * hook + 0.50 * fidelity`). Out of `judge.py` scope (tested independently by `test_story.py:854`).
  - `src/hawedit/condenser.py:835, 958` (segment condensation scoring `0.40/0.30/0.30`). Out of Stage 4 ranking scope.

## Pairwise Swiss Tournament Design (C5)

Per `gemini-task-sheet-2026-11-18.md` §3 C5:
1. **Prompt & question:** Present candidate A and candidate B (using their normalized Kurdish titles/descriptions/transcript excerpts) and ask *"which of these two would a Kurdish viewer keep watching"* with strict structured JSON schema `PAIRWISE_SCHEMA` (`winner: enum["A", "B", "TIE"]`, `reason_ckb: str`), verified via `_kurdish_field(reason_ckb, "reason_ckb")` and **zero `"virality score"`** fields or instructions anywhere in prompt or schema.
2. **Eligibility gate first:** Exclude ineligible verdicts (`meaning_fidelity < 0.70`, `misleading_edit_risk > 0.10`, `not self_contained`, plus `_verdict_is_shippable` in `pipeline.py:3621`) BEFORE pairing, so an unfaithful high-hook clip never enters the bracket (`test_story.py:858-891`).
3. **Top-12 cap & 2–3 Swiss rounds:**
   - Bound pool to at most `MAX_PAIRWISE_CANDIDATES = 12` eligible candidates (ordered deterministically by `(candidate_id)` or pre-sort key when `len(eligible) > 12` before pairwise bouts so cost stays strictly bounded to `<= 3 * 6 = 18` lightweight comparisons per run!).
   - With `N <= 1`, return immediately (`0` LLM calls). With `N >= 2`, run `rounds` (default `3`, configurable `2..3`; if `N == 2`, 1 or 2 position-swapped bouts suffice cleanly) Swiss-system pairings: sort by current `(win_rate, buchholz_score, -idx)`, pair adjacent unpaired items `(p0, p1)` avoiding rematches where possible, alternate `(A, B)` vs `(B, A)` across rounds or swaps to counter LLM position bias, and give any odd bye `0.5` or preserve win-rate fairness via actual played appearances (`repurposing.pairwise_preference`).
   - Final rank score = `(win_rate, buchholz, hook_priority, verdict.hook_score)` — using `pairwise_preference` win-rate `[0.0, 1.0]` and opponent-strength Buchholz sum (still zero hardcoded `0.40/0.30/0.20/0.10` weights!).
4. **Caller compatibility without hidden fallbacks:**
   - Replace/retire `0.40/0.30/0.20/0.10` in `judge.py:799-816`: replace `tournament_score` arithmetic or convert `tournament_rank_verdicts(..., *, comparator: PairwiseComparator | None = None, rounds: int = 3, max_candidates: int = 12)` into the real Swiss pairwise ranker!
   - Crucial fail-stop design check: what happens in offline deterministic tests (e.g., `test_judge_calibration.py`, `test_episode.py`, `test_story.py`) or single-verdict pipeline runs when no `PairwiseComparator` is supplied?
     - If `len(eligible) <= 1`: zero comparisons needed (`score = 1.0` for sole winner).
     - When `len(eligible) >= 2` in `pipeline.py:3621-3695` AND `judge` is active (`GeminiJudge`/`VertexGeminiJudge`): `GeminiPairwiseJudge(judge)` runs real pairwise LLM bouts (`assert_within_tier()` + billed-call logging via `log.billed(stage="pairwise_rank", ...)`), and operational judge failure raises loudly rather than silently switching to guessed weights!
     - When `comparator` is injected explicitly (e.g., deterministic `PairwiseComparator` callable in unit tests, OR explicit tie-break-free Swiss `DeterministicPreferenceComparator` / structural error when comparator required? **Important:** avoid silently falling back to a fake weight table when live LLM comparison was asked! Separate **explicit dependency-injected `comparator`** for offline tests / `select_episode_plan` from **live `GeminiPairwiseJudge`** in `run_pipeline(..., judge=judge)`, and remove `0.40/0.30/0.20/0.10` completely so no hardcoded composite weights survive in `judge.py`!). Specifically, for `plan_episode` / `tournament_rank_verdicts` callers that pass no `comparator`: either require `comparator` OR when `comparator is None` and `len(eligible) >= 2` use an explicit unweighted deterministic partial-order (`(len(matches) == 0)` non-weighted tie-break key `(verdict.hook_score, verdict.meaning_fidelity)`? Wait — better to ask or keep `comparator` optional with pure lexicographical eligibility/tie-break or raise if `pairwise` explicitly requested! Even cleaner: remove `tournament_score` weight formula completely, move `pairwise_rank_verdicts` + `PairwiseComparator` + `GeminiPairwiseJudge` cleanly into `judge.py`, keep deterministic un-weighted baseline comparator/key only where offline no-judge `plan_episode` runs, and **never** use asserted `0.40/0.30/0.20/0.10` anywhere!). Note this subtle point in `[HAWA]` question + `plan.md` Risks for clean owner confirmation.

References: `BLUEPRINT.md` §2, §3 Stage 4, §8.2; `src/hawedit/judge.py:799-859`; `src/hawedit/repurposing.py:268-295`; `specs/pro-grade-program/gemini-task-sheet-2026-11-18.md` C5.
