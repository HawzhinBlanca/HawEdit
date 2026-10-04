# Production ASR First-Failure Impact Map

Pre-edit actual Serena definitions/references: asr-stop-before-map.json. The successful
earlier asr-admission-before-v3-map.json is retained as supplementary unchanged-source
impact, not a replacement for the fresh targeted map. Warnings remain in original logs.

- `asr.transcribe_prepared_segments`: native `OmniAsrProducer.transcribe`, WSL
  `asr_worker.run_request`, direct diagnostics in `tests/test_asr.py`. Production callers
  opt into first-failure behavior; diagnostic calls retain accounting.
- `asr._validate_hard_segments`: native producer and WSL worker. Preserve original input
  and correction records; production now raises rather than returning a successful raw.
- `asr._assemble_canonical_transcript`: producers and direct diagnostic tests. Raw schema,
  offsets, adapter identity, confidence and failure semantics stay unchanged.
- `asr_worker.run_request`: CLI `main`, host WSL invocation and tests in `test_asr.py` /
  `test_adapter_identity.py`. Existing schema 2 request/source identity unchanged; failing
  production does not publish its output file.
- `pipeline.run_pipeline`: CLI/shared builder, durable worker, tests, smoke/real-media
  drivers. Refusal uses existing StageSkipped/PipelineRun/events contracts; both supplied
  and source/producer-bound raw reuse land at the same admission boundary.
- `test_wsl_worker_retains_canonical_alignment_when_validator_correction_is_infeasible`:
  pytest-discovered entrypoint, no source caller. Update its obsolete production-success
  assumption visibly; keep original diagnostic preservation assertions and assert no
  production output after the approved halt.

Complete caller suites: test_asr, test_adapter_identity, test_pipeline, test_transcripts,
test_events, test_durable, test_studio_generation; exact full gate follows. New helper and
test symbols were mapped before adoption in asr-stop-helpers-map.json and
asr-stop-assertions-map.json. Final actual 19-query map is asr-stop-final-map.json;
pipeline references 195, native transcribe 9, worker 16, draft helper 15, validation
helper 5, failure class 5, new guard 1. Pytest entrypoints have no source callers;
containing-symbol warnings are retained, not evidence of zero runtime use.

Original source/raw/model/harness/security review bytes remain unchanged. The first real
replay invalidated the historical ingest cache under its existing configuration binding,
copied six files to recovery and rebuilt Stage 0. Its unchanged-file check failed and is
retained. See asr-stop-verification.md; do not claim original Stage 0 file identity stayed
unchanged or that the old checkpoints prove new completion.
