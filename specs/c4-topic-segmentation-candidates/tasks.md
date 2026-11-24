# Tasks ledger — c4-topic-segmentation-candidates
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  Implement `SentenceEmbedder` Protocol and zero-API `SoraniTfIdfEmbedder` reusing `index_tokens` + `character_ngrams` in `src/hawedit/topic_segmenter.py`, refusing raw transcripts   (tests: test_topic_segmenter_refuses_raw_transcript, test_sorani_embedder_captures_topic_cohesion_with_clitics)
- [x] T2  Implement clean-room MIT TextTiling depth scoring and duration-bounded (`30–90 s`) sentence-complete `discover_topics` emission   (tests: test_texttiler_splits_at_topic_shift_with_sentence_complete_spans, test_topic_segments_respect_min_and_max_duration_bounds, test_topic_segmenter_handles_short_inputs_and_refuses_invalid_params)
- [x] T3  Add `combine_verbal_candidates` in `discovery.py`, wire `--topic-candidates` / `topic_candidates` in `pipeline.py`, update `README.md` + `PROGRESS.md` module map, and record ADR `D-345`   (tests: test_topic_candidates_merge_with_path_a_preserving_unique_wins, test_pipeline_discovers_topic_candidates_without_api)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
