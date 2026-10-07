# EARS Requirements

- E1 WHEN a complete or middle ledger record is malformed, THE reader SHALL
  refuse with record context rather than hide later events, preserving bytes.
  Tests: test_event_replay_refuses_corrupt_complete_or_middle_record;
  test_event_replay_refuses_complete_invalid_final_record.
- E2 WHEN the unterminated final JSON record is plausibly incomplete, THE reader
  SHALL return the intact prefix without changing the ledger.
  Test: test_event_replay_tolerates_incomplete_unterminated_final_record.
- E3 WHEN the final JSON record is complete without a newline, THE reader SHALL
  return it; WHEN the actual sink flushes valid records, THE reader SHALL expose
  the real start/billed events including UTF-8 text and CRLF encodings.
  Tests: test_event_replay_accepts_complete_final_record_without_newline;
  test_event_replay_preserves_actual_live_sink_and_billed_roundtrip;
  test_event_replay_accepts_valid_crlf_records.
- E4 WHEN timeline reads corruption or no ledger, THE observer SHALL respectively
  propagate a contextual refusal or preserve its explicit unavailable state.
  Tests: test_event_replay_timeline_refuses_middle_corruption;
  test_event_replay_missing_file_behavior_is_preserved.
- E5 WHEN the ledger contains invalid UTF-8, THE reader SHALL refuse with an
  evidence-preservation diagnostic rather than rewrite or normalize it.
  Test: test_event_replay_refuses_invalid_utf8_without_repairing_bytes.

These are synthetic replay/observer contracts, not actual charges, durable
attempt persistence, ASR/editorial quality or authenticated publication evidence.
