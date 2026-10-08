# EARS

WHEN an actual sink write fails, THE event log SHALL latch persistence
uncertainty, preserving its original cause with a distinct refusal.
Test: test_event_write_failure_is_sticky_after_actual_file_recovery.

WHEN the physical sink recovers, THE same failed log SHALL refuse further
started, finished, billed and health admission without sequence or sink activity.
Test: test_event_write_failure_is_sticky_after_actual_file_recovery.

WHEN a real ingest-completed journal write fails, THE actual pipeline SHALL
propagate persistence refusal instead of returning an ingest-failure report.
Test: test_pipeline_propagates_actual_ingest_event_storage_failure.

WHEN a real SQLite write lock prevents attempt-event persistence, THE log SHALL
remain fenced after lock release and the attempt SHALL retain only committed
events and its running exclusion.
Test: test_attempt_event_fence_retains_failure_after_real_sqlite_lock_recovery.

WHEN malformed event input is rejected before writing, THE log SHALL not fence
healthy storage or consume the next sequence number.
Test: test_invalid_event_does_not_consume_sequence_or_fence_healthy_sink.

WHEN an actual closed legacy file sink rejects emission, THE log SHALL preserve
that original write error and refuse silent continuation.
Test: test_closed_jsonl_sink_latches_original_write_error.
