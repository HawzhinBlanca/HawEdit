# Impact Map — independent-path-b (T4.2)

## Modified Symbols & Call Sites

| File | Symbol / Area | Impact |
|---|---|---|
| `src/hawedit/pipeline.py` | `DEFAULT_NONVERBAL_VISUAL_QUERY` | New constant holding the canonical Sorani non-verbal visual query. |
| `src/hawedit/pipeline.py` | `_visual_retrieval_query` | Takes `seed_path_a: bool = False`. Defaults to `(DEFAULT_NONVERBAL_VISUAL_QUERY, "default:nonverbal")` when no explicit query is provided. |
| `src/hawedit/pipeline.py` | `run_pipeline` | Takes `visual_seed_path_a: bool = False`. Passes to `_visual_retrieval_query`. Runs Path B independently. |
| `src/hawedit/pipeline.py` | `_build_argument_parser` | Adds `--visual-seed-path-a` flag. |
| `src/hawedit/pipeline.py` | `_validate_args` | Allows `--visual` without Path A and without `--visual-query`. Treats `--visual` as valid Stage 3 producer for `--auto-select`. |
| `tests/test_pipeline.py` | `test_path_b_runs_without_a_path_a_seed` | New test proving independent Path B discovery without Path A seed. |
| `tests/test_pipeline.py` | `test_path_b_refuses_the_whole_transcript_when_path_a_has_no_candidate` | Updated to pass `visual_seed_path_a=True` to verify D-154 opt-in seed behavior. |
| `tests/test_pipeline.py` | `test_auto_select_accepts_visual_alone` | New test proving CLI accepts `--visual --auto-select`. |
