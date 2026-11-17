# EARS Requirements

- H1 WHEN history loads, THE studio SHALL label each option with its full job ID,
  recorded date (unknown if invalid), source and truthful state.
  Test: test_history_labels_include_identity_date_and_historical_state.
- H2 WHEN a creator searches, THE studio SHALL filter cached source/job identities
  using trimmed normalized text without a new server request or implicit selection.
  Test: test_history_filter_is_local_and_normalized.
- H3 WHEN the selected job does not match the filter, THE studio SHALL retain it,
  report that fact and preserve its preview and persisted selection.
  Test: test_history_filter_preserves_selection_without_loading_a_job.
- H4 WHEN no job matches, THE studio SHALL report the empty search result separately
  from unavailable/truncated history and allow clearing the query.
  Test: test_history_search_is_semantic_and_announces_results.
- H5 WHEN recorded timestamps are outside supported finite JavaScript dates, THE
  studio SHALL show unknown instead of Invalid Date or an invented current time.
  Test: test_history_dates_refuse_invalid_values.
- H6 WHEN mixed-script diagnostics or stage rows render at narrow widths, THE studio
  SHALL keep list markers inside their bounds without masking page overflow.
  Test: test_history_and_stage_markers_remain_inside_their_boxes.
- H7 WHEN result counts appear in RTL text, THE studio SHALL isolate the numeric
  count/total pair in left-to-right direction so the numerator is not reversed.
  Test: test_history_counts_are_directionally_isolated.

All tests above are structural guards supplemented by actual-browser assertions;
they do not by themselves prove runtime JS behavior, complete AA or native translation.
