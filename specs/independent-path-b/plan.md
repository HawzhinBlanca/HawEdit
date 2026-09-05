# Plan — independent-path-b (T4.2)

Approved-by: Wareen (auto-approved under master true 10/10 acceptance plan)

## Task 1 — Independent Visual Query & Pipeline Integration
1. Define `DEFAULT_NONVERBAL_VISUAL_QUERY` in `src/hawedit/pipeline.py`.
2. Update `_visual_retrieval_query` to default to `(DEFAULT_NONVERBAL_VISUAL_QUERY, "default:nonverbal")` when `seed_path_a=False` and `explicit is None`.
3. Support `visual_seed_path_a: bool = False` in `run_pipeline` and `--visual-seed-path-a` in CLI parser.
4. Update CLI validation to permit `--visual` as an independent Stage 3 producer.

## Task 2 — Verification & Gate
1. Add `test_path_b_runs_without_a_path_a_seed` in `tests/test_pipeline.py`.
2. Add `test_auto_select_accepts_visual_alone` in `tests/test_pipeline.py`.
3. Update `test_path_b_refuses_the_whole_transcript_when_path_a_has_no_candidate` with `visual_seed_path_a=True`.
4. Run `bash scripts/verify.sh` and ensure full gate passes 100% green.
5. Record ADR `## D-271` in `DECISIONS.md`.
6. Flip task in `specs/independent-path-b/tasks.md` and `specs/pro-grade-program/tasks.md`.
