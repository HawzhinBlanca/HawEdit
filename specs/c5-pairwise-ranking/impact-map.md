# Impact map — C5 Pairwise ranking replacing asserted weights

Serena MCP was unavailable in this session, so callers were mapped with `rg -n` over `src/` and `tests/`. Re-run `find_referencing_symbols` before implementation if Serena becomes available.

| Symbol touched / reused | Callers in `src/` | Tests covering them |
|---|---|---|
| `tournament_score` (`src/hawedit/judge.py:799-818`) — **retired** | `judge.py:850` (`tournament_rank_verdicts`), `episode.py:22, 340` (`plan_episode`), `pipeline.py:168, 3686` (`_shippable_sort_key`) | `tests/test_judge_calibration.py:29, 171, 195` (**breaks & updated cleanly** to pairwise ranking) |
| `tournament_rank_verdicts` (`src/hawedit/judge.py:821-859`) | No other callers in `src/` | `tests/test_judge_calibration.py:28, 190, 279`, `tests/test_story.py:19, 891` |
| `pairwise_preference` (`src/hawedit/repurposing.py:268-295`) — **reused** | `repurposing.py` metrics; reused cleanly by new `pairwise_rank_verdicts` in `judge.py` | `tests/test_repurposing.py` |
| `plan_episode`, `select_episode_plan` (`src/hawedit/episode.py:272, 477`) | `pipeline.py:137, 2646` (`_run_episode_delivery`) | `tests/test_episode.py:23-195, 544`, `tests/test_judge_calibration.py:288` |
| `run_pipeline` Stage 4 winner choice (`src/hawedit/pipeline.py:3620-3695`) | `pipeline.py` CLI `main()`, `workflow_control.py` | `tests/test_pipeline.py` |
| **Out-of-scope sibling weights audited** | `src/hawedit/screener.py:167` (`calculate_screener_score`, `0.50/0.35/0.15`, called at `:332, 462`), `src/hawedit/story.py:981` (`rank_editorial_proposals`, `0.50/0.50`), `src/hawedit/condenser.py:835, 958` (`0.40/0.30/0.30`) | `tests/test_screener.py:22-49`, `tests/test_story.py:31, 853`, `tests/test_condenser.py` |

## Findings

- **Complete `src/` caller inventory for `tournament_score`:** Exactly 3 files import/call `tournament_score`: `judge.py:850`, `episode.py:340`, and `pipeline.py:3686`. Updating all three leaves zero dangling references when `0.40/0.30/0.20/0.10` is retired.
- **Preserving `tests/test_story.py:891`:** `test_story.py:891` calls `tournament_rank_verdicts([v_sensational, v_faithful], require_eligible=True)` and expects only `v_faithful` to survive (`v_sensational` fails `meaning_fidelity < 0.70` / `misleading_edit_risk > 0.10`). With `<= 1` eligible item, pairwise ranking emits `0` bouts and returns `[v_faithful]`, so `test_story.py:891` passes unchanged!
- **A5 coordination (`gemini.py` judge model upgrade):** `GeminiPairwiseJudge` delegates HTTP/SDK calls to `GeminiJudge` (`self._judge.generate_json(...)`, `count_parts(...)`), so Lane 1's A5 judge model upgrade automatically upgrades both pointwise Stage 4 judging and C5 pairwise bouts without duplicate routing code or hardcoding model strings in `judge.py`.
- **`tests/test_vex.py` digest pin:** Modifying `judge.py`, `episode.py`, and `pipeline.py` changes `package_digest(src/hawedit)` and requires A3 parking or owner VEX re-pinning on Round 2 merge.
