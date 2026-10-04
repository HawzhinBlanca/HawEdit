# Transcript Start EARS

| ID | Criterion | Named Regression |
|---|---|---|
| TS1 | WHEN ASR producer or transcript cache work begins, THE pipeline SHALL emit exactly one transcript STARTED event before the producer can observe its call. | test_pipeline_transcript_start_precedes_asr_call |
| TS2 | WHEN ASR raises an operational RuntimeError, THE pipeline SHALL emit transcript SKIPPED with the returned report's actual reason, without a completed transcript event. | test_pipeline_asr_refusal_ends_started_transcript |
| TS3 | WHEN a verified canonical transcript is reused, THE pipeline SHALL preserve one ordered transcript start/completion pair without invoking the producer again. | test_pipeline_cached_transcript_preserves_stage_events |
| TS4 | WHEN no transcript producer/input exists, THE pipeline SHALL preserve the actual missing-prerequisite skip and existing sequential event identities. | test_a_run_reports_its_stages_before_it_returns; test_every_skipped_event_carries_the_reason_the_report_carries |

Keep existing completion order, sequence numbers, caller defaults and immutable transcript
contracts. Actual media is decoded for integration tests, but their explicit test producer
is not evidence of real-model accuracy. No skipped regressions, new event enum or fake units.
