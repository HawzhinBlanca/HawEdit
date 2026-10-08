# Impact Map

Actual map f54e67ab5dcec59a65c0ae181b8446c8564035ca346a162617a00180380757d4
in research.md. Source change limited to events.py; no public method removed.

RunEventLog constructor: pipeline.run_pipeline; annotation in
pipeline._run_episode_delivery; test_events; test_event_replay_integrity;
test_run_cost. Constructor adds only internal failure state.

RunEventLog._emit: started and finished. RunEventLog.billed: run_pipeline
discovery and editorial billing observations; event replay/cost tests. Every
emission checks the same sticky fence before validation/sequence/clock/sink.
Failure changes from arbitrary sink exception to distinct RuntimeError subtype;
original exception retained as cause. Control exceptions keep original semantics.

Pipeline's ingest OSError catch no longer catches journal persistence failures.
No pipeline code/signature change. Actual real decoded ingest fault test covers
this caller. Actual episode caller has same event log; successful replay/cost
and complete full suite cover unchanged normal behavior.

run_pipeline direct references: pipeline (2), web (2), tests/test_asr_admission_cache
(5), test_asr_stop (5), test_candidate_framing_parity (2), test_checkpoint (12),
test_episode (2), test_events (10), test_ingest_cache (14), test_pipeline (136),
test_render_boundary_revision (2), test_render_caption_revision (2),
test_review_candidate_cache (4), test_review_findings (2), test_run_cost (2),
test_screener (4). Counts are actual Serena reference records, not test counts.
All remain in the exact full suite; no argv/producer changes.

AttemptStore.append/finish are unchanged. New real-lock event-fence regression
uses actual private source/submission and actual SQLite append; it checks that
the same failed log cannot continue after lock release and the attempt remains
running with only committed events. No automatic terminal release/reconciliation.

prepare_studio_execution and GuardedGeminiTransport._send mapped for future
protected-producer admission only; unchanged, no new model/provider effects.
JsonlEventSink unchanged; actual closed-handle test covers failure identity.
