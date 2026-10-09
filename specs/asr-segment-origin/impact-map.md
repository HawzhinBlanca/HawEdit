# Caller Impact

Actual maps and hashes are in research.md; no signatures invented.

- _validate_hard_segments: OmniAsrProducer.transcribe, asr_worker.run_request,
  tests/test_asr_stop.py. Two production callers currently unpack three results.
- _assemble_canonical_transcript: those producers plus stop/ASR diagnostics.
  Aborted original diagnostic results must not claim completed origins.
- RawTranscript construction/post-init/serde/store: ASR, pipeline, normalization,
  checkpoint/durable, transcript integrity, billing, review and benchmark callers.
  Existing JSON/digest and four-field resume records stay unchanged when absent.
- scores_from_transcript: pipeline.run_pipeline and PipelineRun.to_dict.
  Traced reports use ORIGINAL input confidence/text, not corrected routing.
- SegmentTranscript and select_for_validation: unchanged. Registered model,
  alignment and strict stop contracts remain applicable at both producer sites.

Whole affected tests: asr_origin, asr, asr_stop, asr_context, asr_resume,
asr_worker_diagnostics, asr_completion, asr_admission_cache, asr_model_lifecycle,
transcripts, escalation, adapter_identity, pipeline, checkpoint, durable,
screener_integrity, studio_billing, review_findings, audit_regressions, bench,
claims. Exact verify.sh and same-SHA CI remain required.
