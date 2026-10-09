# Diagnostic Language EARS

All named tests below are initially PLANNED, not evidence of passing behavior.

- WHEN a known history/candidate/recovery diagnostic appears, THE studio SHALL
  show its Sorani explanation without translating or rewriting server records.
  Test: test_studio_known_diagnostics_have_sorani_explanations.
- WHEN a diagnostic code is unknown, THE studio SHALL show a generic Sorani
  uncertainty explanation and retain the original code/message, never claim success.
  Test: test_studio_unknown_diagnostics_keep_original_technical_evidence.
- WHEN a creator opens technical details, THE studio SHALL expose original
  code, job identity and message as safe text with mixed-script isolation.
  Test: test_studio_diagnostic_details_are_semantic_and_text_only.
- WHEN job selection changes, THE studio SHALL clear prior diagnostics before
  asynchronous reads and render the current candidate/recovery diagnostics only.
  Test: test_studio_job_diagnostics_are_cleared_and_adopted.
- WHEN a diagnostic list is rendered, THE studio SHALL keep list markers/text
  inside the responsive layout and announce contextual errors.
  Test: test_studio_job_diagnostic_list_preserves_accessibility_contract.
- WHEN technical details expand with keyboard focus, THE studio SHALL place
  original identity text below the disclosure focus border without overlap.
  Test: test_studio_diagnostic_identity_clears_disclosure_focus_border.

Structural tests are not browser execution, native-editor translation acceptance,
complete AA or generation/review/export evidence. Actual browser coverage and
whole exact committed gate/current CI remain separate requirements.
