# Spec: Clip-Scoped Final ASR (`specs/b2-clip-scoped-final-asr`)

EARS acceptance criteria (`WHEN <trigger>, THE <system> SHALL <response>`). Every criterion names the automated test(s) that verify it in `tasks.md`.

## AC1 — Context-region selection with 3–5 s padding
- WHEN clip-scoped final ASR plans regions for one or more chosen clip spans over Stage 0 `ingested.speech` with `clip_asr_pad_ms` (default `4000`, bounded `[3000, 5000]`), THE planner SHALL first compute episode `_contextual_speech_regions(ingested.speech)` and SHALL select in chronological order every unique region whose `[start_ms, end_ms]` overlaps `[max(0, clip_in_ms - pad_ms), min(duration_ms, clip_out_ms + pad_ms)]` without splitting or resizing any `_ContextSpeechRegion`.
  - Tests: `tests/test_clip_scoped_asr.py::test_padded_clip_region_planner_preserves_episode_context_bounds`, `tests/test_clip_scoped_asr.py::test_padded_clip_region_planner_rejects_padding_outside_3_to_5_seconds`, `tests/test_clip_scoped_asr.py::test_context_region_subset_is_idempotent_under_context_grouping`.

## AC2 — Multi-clip batch deduplication
- WHEN an episode delivery plan selects `N > 1` overlapping or nearby clips, THE pipeline SHALL deduplicate overlapping `_ContextSpeechRegion` items across all `N` padded clip spans and invoke `canonical_asr.transcribe(...)` at most once per episode run over the sorted union of required regions.
  - Tests: `tests/test_clip_scoped_asr.py::test_episode_delivery_batches_all_selected_clips_into_single_asr_call`, `tests/test_clip_scoped_asr.py::test_adjacent_clips_deduplicate_shared_padding_regions`.

## AC3 — Two-pass CLI gating and draft-transcript handoff
- WHEN `--clip-scoped-asr` is passed with `--omni-asr` and a Stage 1 draft source (`--transcript PATH`, or a future draft producer such as B3), THE CLI SHALL run discovery, Stage 4 judging/selection, and initial Stage 5 span planning against the draft transcript before running `canonical_asr` on only the chosen padded spans; WHEN `--clip-scoped-asr` is passed without `--omni-asr` or without a draft source, THE CLI SHALL refuse before Stage 0.
  - Tests: `tests/test_pipeline.py::test_cli_refuses_clip_scoped_asr_without_omni_asr_and_draft_source`, `tests/test_clip_scoped_asr.py::test_single_clip_two_pass_runs_draft_for_selection_and_final_asr_for_render`.

## AC4 — Parity with whole-episode final ASR
- WHEN the same `OmniAsrProducer` / `WslOmniAsrProducer` backend (with identical decoder weights and validation mode) runs over clip-scoped padded regions vs the full episode, THE per-clip final caption text (`Word.w` surfaces and `raw_clip_text`) and CTC-3B word timings (`Word.start_ms`, `Word.end_ms`) within `[clip_in_ms, clip_out_ms]` SHALL match the whole-episode run identically.
  - Tests: `tests/test_clip_scoped_asr.py::test_clip_scoped_caption_text_and_word_timings_match_whole_episode_run`.

## AC5 — Write-once isolation and reusable cache keying (D-136, Invariant #1)
- WHEN clip-scoped final ASR completes, THE system SHALL persist the clip-scoped `RawTranscript` under a separate immutable store namespace (`<work_dir>/clip_asr/transcripts`) leaving the episode draft `work_dir/transcripts` untouched, and `reusable_raw` SHALL miss whenever the selected region bounds, `subset_audio_sha256`, `producer_id`, `source_sha256`, or `admission_policy` change.
  - Tests: `tests/test_clip_scoped_asr.py::test_clip_scoped_store_never_overwrites_draft_raw_and_reuses_exact_region_subset`, `tests/test_clip_scoped_asr.py::test_clip_scoped_cache_misses_when_selected_clip_spans_change`.

## AC6 — Fail-stop, complete-sentence re-anchoring, and wall-time reporting
- WHEN final clip-scoped transcription fails (runtime error, `UnalignedSpeech`, or `AsrProductionFailure`) or leaves no complete final sentences spanning the clip, THE pipeline SHALL halt/skip delivery honestly without silently falling back to the draft transcript for captions or word timings; on success, `PipelineRun.to_dict()` SHALL record measured `clip_scoped_asr_wall_s`, `clip_scoped_asr_regions`, and `clip_scoped_asr_audio_ms` alongside episode duration.
  - Tests: `tests/test_clip_scoped_asr.py::test_clip_scoped_asr_failure_never_falls_back_to_draft_captions`, `tests/test_clip_scoped_asr.py::test_clip_scoped_asr_re_segments_final_words_and_records_wall_time`.
