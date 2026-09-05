# Tasks — independent-path-b (T4.2)

- [x] T1 Implement `DEFAULT_NONVERBAL_VISUAL_QUERY` and decoupled Path B visual query resolution in `src/hawedit/pipeline.py`.
- [x] T2 Support `--visual-nonverbal` and update CLI validation to accept `--visual --visual-nonverbal` as an independent Stage 3 producer.
- [x] T3 Add tests (`test_path_b_runs_without_a_path_a_seed`, `test_auto_select_accepts_visual_alone_using_default_nonverbal_query`) in `tests/test_pipeline.py`, update `security/wsl-asr-vex.json`, pass the gate, and record D-271.
