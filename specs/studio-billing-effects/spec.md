# EARS Specification

- WHEN the supervisor inspects an empty bound journal, THE transport SHALL return
  zero reservations/effects without egress or logical journal writes
  (test_studio_effects_empty_observation_is_read_only).
- WHEN confirmed calls exist, THE transport SHALL return immutable selected-pool
  call identities/states/reservations without request/response content or invoice
  inference (test_studio_effects_confirmed_metadata_is_not_response_or_invoice).
- WHEN a generation outcome is uncertain, THE transport SHALL retain and report
  its intent/reservation without replay/refund
  (test_studio_effects_uncertainty_is_observed_without_replay).
- WHEN another job in the same pool has an intent, THE transport SHALL include it
  (test_studio_effects_includes_other_job_uncertainty).
- WHEN another pool exists, THE transport SHALL validate its raw rows before
  filtering selected-pool metadata (test_studio_effects_filters_only_after_validation).
- WHEN raw journal identity/arithmetic/evidence or storage binding differs, THE
  transport SHALL refuse inspection while preserving retained evidence
  (test_studio_effects_refuses_corrupt_foreign_rows,
  test_studio_effects_refuses_changed_database_identity).
- WHEN supplied inspection limits are boolean, nonfinite, malformed or outside
  bounded ranges, THE transport SHALL return an actionable storage refusal and
  preserve evidence (test_studio_effects_invalid_read_limits_are_actionable,
  test_studio_effects_bounded_inspection_preserves_evidence).
- WHEN selected owner proof is revoked before or during inspection, THE signed
  transport SHALL refuse without egress or accepting a supplied authority flag
  (test_signed_studio_effects_reopens_raw_authority,
  test_signed_studio_effects_rechecks_after_actual_sqlite_read).
- WHEN a signed observation is valid, THE transport SHALL use the real underlying
  private journal and expose no publication/quiescence capability
  (test_signed_studio_effects_is_descriptive_only).

No observation SHALL authorize process quiescence, new spending, refunds,
automatic uncertain replay, terminal job state or publication. Current gate and
same-SHA CI plus full acceptance remain required separately.
