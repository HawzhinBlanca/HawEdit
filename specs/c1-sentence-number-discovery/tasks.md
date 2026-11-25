# Tasks ledger — c1-sentence-number-discovery
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  Remove `_timing_table(limit=4000)`; switch `CANDIDATE_SCHEMA` and `_PROMPT` to 0-based numbered sentences across all sentences   (tests: test_prompt_sends_all_numbered_sentences_past_4000_words, test_the_whole_transcript_is_sent_unfiltered, test_candidate_schema_uses_sentence_numbers_not_milliseconds)
- [x] T2  Map `[start_sentence..end_sentence]` to exact CTC `Sentence` timestamps and fail-stop (`JudgeUnusable`) on invalid or incomplete boundaries; preserve invariant #3   (tests: test_sentence_indices_map_to_exact_ctc_word_boundaries, test_invalid_or_incomplete_sentence_indices_raise_judge_unusable, test_the_judge_reads_the_normalized_transcript_never_the_raw_one, test_discovery_finds_moments_past_4000_words)
- [x] T3  Bind cache key to sentence boundaries, wire `sentences` cleanly in `pipeline.py:3289`, update affected `test_path_a.py` fixtures, and record ADR `D-344`   (tests: test_cache_key_binds_sentence_boundaries, test_pipeline_passes_segmented_sentences_to_path_a)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
