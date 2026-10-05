# EARS Requirements

- A1 WHEN no raw diagnostic evidence or partial records exist, THE report SHALL
  mark ASR diagnostics unavailable and emit null rather than zero/empty measurements.
  Test: test_missing_asr_evidence_reports_unknown_not_zero.
- A2 WHEN partial diagnostic records exist without the raw transcript, THE report
  SHALL preserve them, label them partial, and leave total coverage unknown.
  Test: test_partial_asr_diagnostics_do_not_claim_complete_coverage.
  Additional test: test_partial_asr_correction_and_routing_records_remain_visible.
- A3 WHEN the raw transcript has passed the existing integrity check, THE report
  SHALL expose its recorded diagnostics, including genuine zero values.
  Tests: test_a_run_with_nothing_missing_reports_zero_rather_than_omitting_the_key,
  test_raw_diagnostics_are_the_reporting_source.
- A4 WHEN production refuses known damaged raw evidence, THE report SHALL preserve
  the measured gaps and refusal rather than claim completion.
  Tests: test_the_report_says_which_speech_has_no_transcription; test_asr_stop.py.

Recorded diagnostic availability is not native accuracy or publication approval.
