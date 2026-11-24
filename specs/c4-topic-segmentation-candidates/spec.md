# Spec — C4 Topic-segmentation candidates (`c4-topic-segmentation-candidates`)

EARS criteria. Each names the automated test(s) that will verify it in `tests/test_topic_segmenter.py` (and `tests/test_pipeline.py` for wiring).

- **AC1** WHEN `SoraniTfIdfEmbedder` or `segment_topics` receives a `RawTranscript`, THE system SHALL refuse with `TypeError` (Kurdish invariant #3) without computing embeddings or candidates.
  `test_topic_segmenter_refuses_raw_transcript`
- **AC2** WHEN Sorani sentences contain §4.1 morphological/clitic variants (`کتێب` vs `کتێبەکەم`) or encoding collisions (`ي`/`ك` -> `ی`/`ک`), THE default Sorani embedder SHALL produce higher cosine similarity within the same topic block than across unrelated topic blocks using normalized word tokens and character 3-grams offline with zero network calls or GPU usage.
  `test_sorani_embedder_captures_topic_cohesion_with_clitics`
- **AC3** WHEN a multi-topic transcript shifts sharply between distinct topics, THE TextTiling depth scorer SHALL locate the topical boundary peak at the transition sentence gap and emit contiguous sentence-complete `Candidate` spans with exact CTC timestamps `(sentences[i].start_ms, sentences[j].end_ms)` and `path == DiscoveryPath.VERBAL`.
  `test_texttiler_splits_at_topic_shift_with_sentence_complete_spans`
- **AC4** WHEN raw topic segments fall outside `[min_span_ms, max_span_ms]` (default `[30_000, 90_000]` ms), THE segmenter SHALL split over-long segments at deepest internal depth valleys and merge adjacent under-short segments across shallowest valleys along complete sentence boundaries, dropping or refusing unsplittable sub-floor fragments rather than cutting mid-sentence.
  `test_topic_segments_respect_min_and_max_duration_bounds`
- **AC5** WHEN C4 candidates are combined with Path A (and future C3) verbal candidates and passed through `merge_candidates`, THE merger SHALL preserve every unique C4 win without duplicating IDs, altering `DiscoveryPath` beyond `{"verbal", "visual", "both"}`, or overriding primary Path A visual-partner rank precedence.
  `test_topic_candidates_merge_with_path_a_preserving_unique_wins`
- **AC6** WHEN a transcript contains fewer sentences than the block window (`< 2 * block_size` or too short to satisfy `min_span_ms`), THE segmenter SHALL emit `()` cleanly (or raise `ValueError` on invalid parameters such as `block_size < 1` or `min_span_ms <= 0`) with zero fake scores or NaN vectors.
  `test_topic_segmenter_handles_short_inputs_and_refuses_invalid_params`
- **AC7** WHEN `run_pipeline` runs with `topic_candidates=True` (no Gemini key required), THE pipeline SHALL discover Stage 3 C4 candidates deterministically offline into `run.candidates` and record Stage 3 discovery provenance in `PipelineRun`.
  `test_pipeline_discovers_topic_candidates_without_api`
