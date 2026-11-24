# Tasks: Clip-Scoped Final ASR (`specs/b2-clip-scoped-final-asr`)

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"

All tasks follow `AGENTS.md` (test-first, smallest correct change, single-writer worktree `HawEdit-lane-2`, gate pass via `scripts/verify.sh` on lead before flipping ledger rows).

- [x] T1 Implement `select_contextual_regions_for_spans` in `src/hawedit/asr.py` (`3000–5000 ms` pad bounds, episode `_contextual_speech_regions` snapping, deduplication, ordering, AC1 tests in `tests/test_clip_scoped_asr.py`: `test_padded_clip_region_planner_preserves_episode_context_bounds`, `test_padded_clip_region_planner_rejects_padding_outside_3_to_5_seconds`, `test_context_region_subset_is_idempotent_under_context_grouping`).
- [x] T2 Wire `--clip-scoped-asr` / `--clip-asr-pad-ms` and shared draft -> batched clip-scoped final ASR -> complete-sentence re-anchoring + isolated `work_dir/clip_asr/transcripts` store + wall-time reporting in `src/hawedit/pipeline.py` (AC2–AC6 tests in `tests/test_clip_scoped_asr.py` & `tests/test_pipeline.py`: `test_clip_scoped_caption_text_and_word_timings_match_whole_episode_run`, `test_episode_delivery_batches_all_selected_clips_into_single_asr_call`, `test_clip_scoped_store_never_overwrites_draft_raw_and_reuses_exact_region_subset`, `test_clip_scoped_asr_failure_never_falls_back_to_draft_captions`, `test_single_clip_two_pass_runs_draft_for_selection_and_final_asr_for_render`, `test_cli_refuses_clip_scoped_asr_without_omni_asr_and_draft_source`, `test_the_case_table_is_bound_bidirectionally_to_every_preflight_refusal`).
- [x] T3 Record ADR `D-340` in `DECISIONS.md`, coordinate VEX digest pin update at integration, and measure real GPU-1 clip-scoped vs whole-episode text/word-timing parity & wall time on `zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4` and `RO1PmSoqmCM` into `evidence/b2-clip-scoped-asr-2026-11-19.md` (`test_every_decision_the_docs_cite_exists`, `test_every_value_the_decision_log_states_is_the_value_the_code_holds`, `test_new_evidence_names_its_commit_media_and_host`).

## Definition of Done
- AC1–AC6 unit and parity tests pass in full `verify.sh` and CI.
- Real-media measurement in `evidence/` demonstrates identical per-clip caption text & word timings to a whole-episode run on the same spans, plus measured wall time with full HawaPC01 provenance.
