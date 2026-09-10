# Proposed EARS acceptance criteria

Research SHA: `532e6efb1708e8dc2c3d14dde4fb7927f5115006`.
Status: proposed tests, not implemented or passing claims. Approved-by: pending for new implementation.

| ID | Criterion | Proposed test |
|---|---|---|
| RB-01 | WHEN a job is submitted with non-media bytes, THE API SHALL reject it with a typed validation result before scheduling processing. | `test_api_rejects_nonvideo_source_before_enqueue` |
| RB-02 | WHEN two different source assets complete, THE app SHALL return each job's own validated manifest and matching source digest. | `test_app_two_sources_return_their_own_rendered_artifacts` |
| RB-03 | WHEN distinct jobs are submitted rapidly, THE queue SHALL preserve every accepted job under a unique persistent identifier. | `test_rapid_submissions_preserve_all_distinct_jobs` |
| RB-04 | WHEN the same idempotency key is retried after acceptance, THE API SHALL recover the original job without scheduling a duplicate. | `test_retry_after_acceptance_recovers_existing_job` |
| RB-05 | WHEN a worker stops during a stage, THE workflow SHALL recover or surface an actionable terminal state after lease expiry. | `test_worker_restart_recovers_leased_job` |
| RB-06 | WHEN a required cached artifact is corrupt or missing, THE workflow SHALL invalidate that stage and dependent stages before reuse. | `test_resume_rejects_corrupted_proxy_and_audio` |
| RB-07 | WHEN the effective configuration or producer revision changes, THE workflow SHALL invalidate affected cached results. | `test_resume_invalidates_changed_producer_configuration` |
| RB-08 | WHEN a multi-span plan renders, THE pipeline SHALL preserve source word identity and render the exact ordered source intervals with aligned captions/audio. | `test_multispan_pipeline_renders_distinct_source_segments` |
| RB-09 | WHEN an edit-plan write fails, THE pipeline SHALL expose no newly published incomplete bundle and SHALL report the actual persisted state. | `test_plan_write_failure_cannot_follow_publication` |
| RB-10 | WHEN a review candidate is promoted, THE delivery SHALL contain its validated mandatory plan and all manifest-bound artifacts atomically. | `test_promote_preserves_review_plan_identity_atomically` |
| RB-11 | WHEN a render's declared duration differs materially from decoded duration, THE critic SHALL refuse an all-clear verdict. | `test_critic_rejects_declared_duration_beyond_media` |
| RB-12 | WHEN inspection coverage or source context was not observed, THE critic SHALL report unknown/refused and SHALL not count planned windows as observed. | `test_critic_requires_actual_window_and_source_evidence` |
| RB-13 | WHEN a required face detector or shot schedule is unavailable, THE quality gate SHALL report unavailable/refused instead of pass. | `test_face_check_missing_resources_cannot_pass` |
| RB-14 | WHEN a job fails or its status endpoint becomes unavailable, THE UI SHALL leave indefinite progress and present a recoverable error state. | `test_ui_handles_failed_missing_and_disconnected_jobs` |
| RB-15 | WHEN a selected candidate is offered for playback/download, THE app SHALL verify its media exists and belongs to that candidate's manifest. | `test_all_offered_candidates_are_playable_and_bound` |
| RB-16 | WHEN source/plan/output bytes change after inspection, THE system SHALL invalidate that inspection and any approval derived from it. | `test_artifact_mutation_invalidates_approval` |
| RB-17 | WHEN an external request outcome is uncertain, THE workflow SHALL persist uncertainty and reconcile before automatic resubmission. | `test_uncertain_external_call_is_not_blindly_rebilled` |
| RB-18 | WHEN a professional-quality claim is produced, THE report SHALL identify the evaluated output digest, actual coverage, limitations and rubric version. | `test_quality_report_cannot_claim_unperformed_checks` |

Human editorial acceptance remains necessary beyond automated tests: blinded Sorani meaning/fidelity review, source-context comparison, natural speech listening and publishability. Benchmarks require frozen data splits and explicit eligible-source coverage. Automated assertions about a model's claimed score cannot substitute for these judgments.
