# Resource Preflight EARS

- RP1: WHEN work storage contains a file, hardlink or directory at the old probe
  name, THE preflight SHALL leave that member and its evidence unchanged.
  Test: test_preflight_preserves_existing_probe_name.
- RP2: WHEN the capacity budget is not a non-negative integer, THE preflight
  SHALL raise ResourceCapacityError before creating or writing storage.
  Test: test_preflight_refuses_invalid_budget_before_storage.
- RP3: WHEN actual work-directory preparation fails, THE preflight SHALL report
  ResourceCapacityError with original OSError cause and preserve existing bytes.
  Test: test_preflight_reports_real_directory_failure_without_mutating_evidence.
- RP4: WHEN valid resource probing succeeds, THE preflight SHALL verify an actual
  flushed/synchronized byte roundtrip and remove only its own temporary resource.
  Test: test_preflight_removes_only_its_own_successful_probe.
- RP5: WHEN actual free capacity is below the requested budget, THE preflight
  SHALL refuse without modifying existing evidence or invoking model/publication
  work. Test: test_preflight_capacity_refusal_preserves_existing_evidence; existing
  test_visual_workflow_recovery_preserves_evidence_and_publication_identity.

A resource check is not protected-path confinement, model readiness, human review
or execution/publication authority. Complete signed-worker adoption stays separate.
