# Impact Map

Actual Serena map: asr-segment-checkpoint-map-422-20261006/serena-map.json.

- asr_worker.run_request: CLI main; tests/test_asr.py, test_adapter_identity.py,
  test_asr_completion.py, test_asr_stop.py. Preserve default programmatic contract;
  optional checkpoint argument supports integration diagnostics.
- asr_worker.main: module entry point; enable production checkpoints here.
- transcribe_prepared_segments: native producer and worker; unchanged signature
  and hard-stop semantics. Decorate the operation boundary, not its loop.
- _validate_hard_segments: native producer, worker, ASR/stop tests; unchanged
  global ranking and correction behavior. Cache exact operation inputs only.
- SegmentTranscript/Word: validate loaded results using existing dataclasses;
  no transcript schema change or raw-text rewrite.
- WslOmniAsrProducer.transcribe: pipeline/factory, bridge tests; no change to
  request schema or timeout. Native Linux cache binds the entire request and PCM.
- PrivateDirectory/write_text_atomic: existing studio callers unchanged.

Integration regression files: tests/test_asr.py, test_asr_stop.py,
test_asr_completion.py, test_adapter_identity.py, test_asr_worker_diagnostics.py.
New checkpoint component tests exercise real storage and decoded PCM; injected
model responses test orchestration only, never ASR quality.

Lookup repair map at 0de4732: actual OperationJournal.operation callers are
ResumableBackend.transcribe_segment/align_segment and ResumableValidator.transcribe_segment,
plus component tests. No public signature, output key or production binding change.
All three decorators remain covered by the complete test_asr_resume file. Real
old-source journal replay is labelled component compatibility, never a current-
source production admission or a silent source-binding migration.
