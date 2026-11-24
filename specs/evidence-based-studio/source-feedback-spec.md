# Source Feedback EARS

- SF1: WHEN a creator selects a different source file, THE studio SHALL clear
  feedback and progress from the previous transfer before presenting the new
  source as ready for upload.
  Test: test_studio_ui_source_selection_clears_previous_transfer_feedback.
- SF2: WHEN a creator selects a source file, THE studio SHALL display its exact
  declared byte length without rounding a nonempty source to a zero-size label.
  Test: test_studio_ui_source_selection_reports_exact_file_bytes.
- SF3: WHEN a creator selects a new file, THE studio SHALL invalidate the old
  runnable source/ticket and persisted identity while preserving recovery locks
  and unavailable producer/review/export refusals.
  Test: test_studio_ui_source_selection_preserves_invalidation;
  existing test_studio_ui_superseded_requests_cannot_replace_selection and
  test_studio_semantic_controls_and_no_fabricated_quality.

Automated tests here are structural callback contracts. Actual selected-file
and live-message behavior also requires fresh native browser evidence on
the repaired source. No full workflow/accessibility/quality claim follows.
