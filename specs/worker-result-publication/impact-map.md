# Actual Impact Map

Only existing run_request changes, signature unchanged. Actual current map in
research.md records23references: main, test_adapter_identity, test_asr,
test_asr_completion, test_asr_model_lifecycle, test_asr_origin, test_asr_resume,
test_asr_stop and their imports/cases. main has1entrypoint reference.
WslOmniAsrProducer.transcribe has6direct test references; its subprocess module
invocation reaches worker.main dynamically. _assemble_canonical_transcript
has20references and remains unchanged. TranscriptStore._write_raw_locked has
1internal caller and is a read-only pattern reference, not edited behavior.

Keep whole above caller modules plus test_asr_worker_diagnostics,
test_trusted_producer_parity, test_checkpoint and test_claims in applicable
checks/exact gate. New result/publication/collision tests exercise actual worker
and filesystem with explicit model doubles, not semantic ASR acceptance.
No canonical transcript/serde, model/routing/threshold, checkpoint lease,
producer API, HTTP/DBOS, fixture/golden/harness or dependency change.

New evidence is read by unchanged claims provenance validation; metadata must
cite existing baseline commit, generated PCM hash, host and actual command.
No new source module requiring a README module-map row.
