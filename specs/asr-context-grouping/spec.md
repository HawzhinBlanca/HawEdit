# ASR Context Grouping EARS

1. WHEN canonical factory inputs contain nearby ordered VAD intervals, THE system
   SHALL coalesce whole intervals only within the 1000-ms gap and 38000-ms union
   limits, preserving every original interval exactly once.
   Tests: `test_context_grouping_preserves_complete_intervals_and_respects_limits`.
2. WHEN an existing individual interval is between 38000 and 40000 ms, THE system
   SHALL retain it intact rather than trim it to the grouping budget.
   Test: `test_context_grouping_keeps_supported_long_single_region_intact`.
3. WHEN input is malformed, overlapping or unordered, THE grouping system SHALL
   refuse before inference or source cutting.
   Test: `test_context_grouping_refuses_invalid_input`.
4. WHEN the canonical factory selects native or WSL execution, THE system SHALL
   select the same context policy and retain the unchanged completion policy.
   Test: `test_factory_native_and_wsl_share_context_and_completion_policy`.
5. WHEN a direct constructor uses its existing default, THE system SHALL preserve
   the legacy interval input and admission identity for compatibility.
   Test: `test_direct_producer_context_grouping_remains_explicit`.
6. WHEN context grouping changes effective ASR input, THE system SHALL bind that
   versioned policy into transcript reuse identity; legacy raw data SHALL remain
   immutable and SHALL NOT be silently reused as grouped inference.
   Test: `test_context_policy_cannot_reuse_legacy_raw_binding`.
7. WHEN the native producer cuts a grouped window, THE system SHALL retain target
   and following-region PCM and derive duration from the actual emitted PCM.
   Test: `test_native_context_grouping_cuts_real_pcm_without_dropping_regions`.
8. WHEN context configuration changes during inference, THE system SHALL refuse
   the result rather than bind it to stale configuration.
   Test: `test_native_context_policy_drift_refuses_result`.
9. WHEN canonical ASR fails, THE system SHALL retain the first-failure halt and
   SHALL NOT replace canonical words, trim output, force EOS or publish a result.
   Existing tests: `test_native_production_stops_on_first_asr_failure`,
   `test_native_production_stops_on_first_validator_failure`,
   `test_alignable_repetition_stop_is_refused_before_alignment`.
