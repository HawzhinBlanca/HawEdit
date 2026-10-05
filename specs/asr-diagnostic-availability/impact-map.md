# Caller Impact

Actual Serena map at fd1468a (see research.md), supplemented by field searches:

- PipelineRun construction/replacement: pipeline; signed_pipeline_test_review;
  asr_stop, candidate_framing_parity, durable, events, pipeline,
  render_boundary_revision, render_caption_revision and web tests.
- PipelineRun.to_dict: pipeline CLI and durable_workflow persistence; durable,
  events, pipeline, render_boundary_revision, render_caption_revision and
  run_cost tests. JSON remains serializable, but unavailable diagnostics are null.
- run_pipeline: web and pipeline; asr_admission_cache, asr_stop,
  candidate_framing_parity, checkpoint, episode, events, ingest_cache, pipeline,
  render_boundary_revision, render_caption_revision, review_findings, run_cost
  and screener tests.
- Add optional record at the end of PipelineRun fields to preserve positional
  construction. No other source symbol is changed.

Regression focus: missing producer/failed draft, isolated partial records,
known damaged raw transcript and measured zero. Full gate covers all callers.
