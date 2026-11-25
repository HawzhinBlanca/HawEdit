# Bound Ingest Caller Impact

Baseline45e3726; actual seven-query raw map is ingest-cache-before-map.json. Tool positions
are zero-based. Constructor/protocol dispatch and file-level import fallbacks are dynamic.

| Symbol | Actual affected callers and required coverage |
|---|---|
| run_pipeline |172 refs: own shared builder, legacy web wrapper; checkpoint/episode/events/pipeline/boundary-revision/caption-revision/review-findings/run-cost/screener suites. Signature unchanged; only Stage0 reuse/save implementation changes. |
| _file_digest |3 refs in pipeline; unchanged; current source hash feeds the new cache binding. |
| IngestResult.from_dict |7 refs: pipeline/ingest tests; unchanged signature and validation, called only after matching bounded metadata bytes. |
| StageCheckpoint.from_dict |2 internal checkpoint refs; unchanged; no generic engine rewrite. |
| load_stage_checkpoint |5 test refs; no existing production verifier is inferred. Unchanged. |
| save_stage_checkpoint |12 refs: pipeline/checkpoint/robustness; other stage markers unchanged. Stage0 new bound writer preserves generic marker shape. |
| hash_file |4 test refs; unchanged; new held-file hashing does not promote this existence-only helper into a integrity/security claim. |

New ingest-cache functions have no previous callers. Existing atomic no-replace directory
publication is reused for new owned staging only, not moving original owner directories.
Existing valid cache test forbids recomputation; existing malformed JSON test requires safe
fresh ingest. Keep those assertions and add original-byte retention plus linked/storage/drift
controls. Full gate covers unchanged indirect builder/durable and broader run_pipeline graph.

The mapped run_pipeline body includes the downstream attach_diarization call and former
stage0_json write. Preserve requested diarizer execution and report turns, but do not mutate
base cache after binding. Existing test_an_enabled_diarizer_records_a_measured_success and
test_diarizer_operational_failure_retains_base_ingest_and_continues remain unchanged.
No Diarizer/PyannoteDiarizer signatures or model selection change. Read-only inspection found
no held model identity in that interface, so no turn-reuse authority is inferred.

Supplemental actual Serena map before ingest.py edits: ingest-extract-before-map.json.
_extract_once has2 real callers (extract_audio/extract_proxy); add an internal optional
cached-output validator, not public API flags. _source_digest remains unchanged (4 refs),
and is reused for streamed extraction byte hashing. extract_audio has27 references and
extract_proxy20: ingestion plus complete test_ingest and concurrency suites, including
format failure, truncation, exact reuse and interrupted atomic publication. Public signatures
and existing assertions remain unchanged. The full gate covers their indirect pipeline graph.
