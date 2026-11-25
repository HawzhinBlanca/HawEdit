# Bound Ingest EARS

| ID | Criterion | Named regression |
|---|---|---|
| IC1 | WHEN Stage0 completes, THE pipeline SHALL bind real metadata/audio/proxy bytes and producer/tool/model context into its checkpoint. | test_ingest_checkpoint_binds_actual_output_bytes |
| IC2 | WHEN bound inputs and derived bytes are unchanged, THE pipeline SHALL reuse the actual cache without recomputing it. | test_unchanged_ingest_cache_reuses_exact_files |
| IC3 | WHEN valid derived audio or proxy bytes change, THE pipeline SHALL preserve the prior files and regenerate without passing stale data to ASR. | test_decodable_changed_ingest_media_is_preserved_and_regenerated |
| IC4 | WHEN measured metadata changes, THE pipeline SHALL preserve the record and regenerate measured evidence rather than reuse its new claims. | test_changed_ingest_measurement_is_not_reused |
| IC5 | WHEN a legacy checkpoint lacks derived byte bindings, THE pipeline SHALL expose unverified recovery and preserve it before rebuilding. | test_unverified_legacy_ingest_checkpoint_is_preserved |
| IC6 | WHEN the actual selected tool changes, THE pipeline SHALL invalidate prior cache context without changing model policy. | test_actual_ffmpeg_byte_drift_invalidates_ingest_cache |
| IC7 | WHEN preservation storage fails or cache members are linked, THE pipeline SHALL refuse before ASR without overwriting the original files. | test_ingest_recovery_storage_failure_preserves_originals, test_hardlinked_ingest_cache_is_refused_without_rewriting |
| IC8 | WHEN unreadable metadata requires fresh ingest, THE pipeline SHALL retain original damaged bytes and keep the existing safe-regeneration contract. | test_malformed_ingest_metadata_is_preserved_before_regeneration, test_pipeline_stage0_corrupted_json_falls_back_safely |
| IC9 | WHEN a selected diarizer lacks a bound reusable weight identity, THE pipeline SHALL run that producer and retain its current turns in the report without mutating bound base ingest or adopting another producer's cached turns. | test_diarization_does_not_mutate_or_leak_through_base_ingest_cache |
| IC10 | WHEN a cache file is opened, THE verifier SHALL compare held and path identity while retaining separate complete timestamp baselines and refusing later replacement or new hard links. | test_held_ingest_reader_verifies_real_bytes, test_held_ingest_reader_refuses_changed_bytes, test_held_ingest_reader_refuses_new_hardlink |
| IC11 | WHEN extracted media changes without changing its length or its provenance is size-only legacy evidence, THE extractor SHALL regenerate rather than reuse it, while retaining existing cached-format refusal and interrupted-publication contracts. | test_same_length_changed_extracted_audio_is_regenerated, test_size_only_extraction_provenance_is_not_reused, test_reused_audio_is_still_checked_against_the_format_stage_1_assumes |

- [ ] IC1-IC11: current exact frozen gate and applicable same-SHA CI required. No completed row.
