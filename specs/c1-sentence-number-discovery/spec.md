# Spec — C1 Sentence-number discovery (`c1-sentence-number-discovery`)

EARS criteria. Every criterion names the automated test(s) that verify it in `tests/test_path_a.py` (and `tests/test_pipeline.py` where pipeline integration applies).

- **AC1** WHEN `PathADiscovery` formats a discovery prompt for a `NormalizedTranscript`, THE system SHALL render every sentence as a 0-based numbered line `[i] <normalized sentence text>` with no 4,000-word limit and SHALL remove `_timing_table` millisecond dumps.
  `test_prompt_sends_all_numbered_sentences_past_4000_words`, `test_the_whole_transcript_is_sent_unfiltered`
- **AC2** WHEN raw text (`RawTranscript`) is passed to `PathADiscovery.discover`, `_prompt`, or `build_request`, THE system SHALL refuse with `TypeError` before serializing any prompt or hitting any network transport (Kurdish invariant #3).
  `test_the_judge_reads_the_normalized_transcript_never_the_raw_one`
- **AC3** WHEN `CANDIDATE_SCHEMA` is inspected or validated against Gemini structured output, THE schema SHALL require integer `start_sentence`, integer `end_sentence`, finite `score`, and `reason_ckb`, with neither `in_ms` nor `out_ms`.
  `test_candidate_schema_uses_sentence_numbers_not_milliseconds`
- **AC4** WHEN Gemini returns valid inclusive sentence indices `[start_sentence..end_sentence]` where `sentences[start_sentence:end_sentence+1]` are complete sentences, THE system SHALL map them to exact CTC boundaries `(sentences[start_sentence].start_ms, sentences[end_sentence].end_ms)` with zero guessed milliseconds.
  `test_sentence_indices_map_to_exact_ctc_word_boundaries`
- **AC5** WHEN Gemini returns out-of-range (`< 0` or `>= len(sentences)`), inverted (`end_sentence < start_sentence`), boolean/non-integer sentence indices, or an incomplete trailing fragment boundary (`complete == False`), THE system SHALL raise `JudgeUnusable` with zero silent clamping or fallback to raw word boundaries.
  `test_invalid_or_incomplete_sentence_indices_raise_judge_unusable`
- **AC6** WHEN a long episode exceeds 4,000 words (e.g., 5,000+ words / 100+ sentences), THE prompt SHALL stay un-truncated across all sentences and `PathADiscovery` SHALL discover candidates past word 4,000 cleanly without dropping timings.
  `test_discovery_finds_moments_past_4000_words`
- **AC7** WHEN `PathADiscovery.discover` runs K-run caching or `run_pipeline` calls Stage 3 discovery at `pipeline.py:3289`, THE cache key SHALL bind sentence boundaries as well as transcript text and `run_pipeline` SHALL pass its segmented `sentences` through cleanly without breaking `assemble_spans` or `_judgeable_plans`.
  `test_cache_key_binds_sentence_boundaries`, `test_pipeline_passes_segmented_sentences_to_path_a`
