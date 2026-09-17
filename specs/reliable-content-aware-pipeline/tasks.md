# Task sequence — reliable content-aware pipeline

Approved-by: Wareen (via /goal implement in `plan.md`).

Every row is proposed and unchecked. Read the linked specification for full EARS requirements. Named tests are planned tests, not present/green evidence. A row is accepted only after the canonical gate, required media evidence and exact-SHA required CI; only `scripts/update-ledger.sh` may flip rows.

- [x] T00 Freeze actual baseline, source/runtime manifest, eligible domain and episode-disjoint study protocol
- [x] T01 Rejected/unknown QC cannot authorize delivery; revisions invalidate old final-media review
- [x] T02 Final render stays private and reviewable; approval promotes the same bytes without rerender
- [x] T03 Caption verification rejects textured no-caption footage and damaged text/geometry
- [x] T04 Canonical and revision routes use the shared claim-verification boundary for all crop modes
- [x] T05 One resolved configuration defines the exact behavior before expensive work
- [x] T06 One retained-interval mapping drives every export and media clock
- [x] T07 Trimming protects quiet speech, uncertain regions and meaningful pauses/reactions
- [x] T08 Candidate context is canonical, contiguous, source-linked and preserved or refused
- [ ] T09 Independent discovery and shared ranking obey coverage, integrity and budget constraints
- [ ] T10 Tracker handles off-screen speakers/listener shots and resets at scene cuts
- [ ] T11 Shot layout stays stable on ambiguity and responds to verified sustained changes
- [ ] T12 One restrained caption policy reads well on phones and preserves canonical text
- [ ] T13 Final audio meets the existing contract and conditioning is supported by listening evidence
- [ ] T14 Episode CLI produces up to N actual distinct deliveries with shared preprocessing and honest item states
- [ ] T15 Restart/duplicate submission preserve verified work and publish once
- [ ] T16 Unknown billed outcomes and retries remain persisted, bounded and explicit
- [ ] T17 Real process/storage/runtime faults preserve primary reasons, cleanup and delivery integrity
- [ ] T18 Relevant changes invalidate only dependent artifacts; schema/release rollback works
- [ ] T19 Independent holdout, blind comparisons, current gate/CI and owner review produce a scoped acceptance report
- [ ] T20 A fresh holdout and representative use window substantiate sustained acceptance

| Task | Dependency | Smallest observable outcome | Criteria / proposed test evidence |
|---|---|---|---|
| [ ] T00 | Plan approval | Freeze actual baseline, source/runtime manifest, eligible domain and episode-disjoint study protocol. | AC-24; `test_acceptance_split_has_no_episode_or_speaker_leakage`, `test_scorecard_counts_refusals_and_all_proposed_clips` |
| [ ] T01 | T00 | Rejected/unknown QC cannot authorize delivery; revisions invalidate old final-media review. | AC-03–AC-04; `test_boundary_revision_does_not_rebind_previous_review`, `test_caption_revision_requires_review_of_new_bytes`, `test_cli_rejected_qc_record_cannot_authorize_delivery` |
| [ ] T02 | T01 | Final render stays private and reviewable; approval promotes the same bytes without rerender. | AC-01–AC-02; `test_unreviewed_render_is_retained_privately_for_review`, `test_approved_candidate_promotes_identical_bytes_without_render` |
| [ ] T03 | T02 | Caption verification rejects textured no-caption footage and damaged text/geometry. | AC-05–AC-06; `test_textured_background_cannot_prove_caption_presence`, `test_caption_verification_detects_wrong_text_and_broken_joining` |
| [ ] T04 | T03 | Canonical and revision routes use the shared claim-verification boundary for all crop modes. | AC-07; `test_all_claimed_crop_modes_use_matching_verification`, `test_opening_subject_check_runs_through_default_pipeline` |
| [ ] T05 | T04 | One resolved configuration defines the exact behavior before expensive work. | AC-08; `test_effective_configuration_preserves_explicit_overrides`, `test_incompatible_configuration_refuses_before_model_load` |
| [ ] T06 | T05 | One retained-interval mapping drives every export and media clock. | AC-09–AC-10; `test_trimmed_render_and_all_sidecars_share_one_time_mapping`, `test_vfr_and_fractional_rate_keep_audio_caption_and_edit_alignment` |
| [ ] T07 | T06 | Trimming protects quiet speech, uncertain regions and meaningful pauses/reactions. | AC-11; `test_silence_policy_preserves_quiet_speech_and_protected_beats` |
| [ ] T08 | T07 | Candidate context is canonical, contiguous, source-linked and preserved or refused. | AC-12–AC-13; `test_candidate_retains_question_and_qualification_or_refuses`, `test_editorial_proposal_rejects_unverifiable_source_references` |
| [ ] T09 | T08 | Independent discovery and shared ranking obey coverage, integrity and budget constraints. | AC-14–AC-15; `test_discovery_paths_remain_independent_with_full_coverage`, `test_transcript_instructions_cannot_change_policy_or_approve_qc`, `test_single_and_episode_modes_share_eligibility_and_ranking` |
| [ ] T10 | T09 | Tracker handles off-screen speakers/listener shots and resets at scene cuts. | AC-16; `test_visible_listener_is_not_assigned_to_offscreen_speaker`, `test_scene_cut_resets_invalid_speaker_spatial_state` |
| [ ] T11 | T10 | Shot layout stays stable on ambiguity and responds to verified sustained changes. | AC-17; `test_layout_policy_holds_on_ambiguity_and_switches_on_verified_turn` |
| [ ] T12 | T11 | One restrained caption policy reads well on phones and preserves canonical text. | AC-06, AC-18; `test_mobile_caption_layout_preserves_canonical_sorani`; real phone-size review required |
| [ ] T13 | T12 | Final audio meets the existing contract and conditioning is supported by listening evidence. | AC-18; `test_final_audio_is_measured_after_conditioning_and_encode`; ADR for D-264 behavior change |
| [ ] T14 | T13 | Episode CLI produces up to N actual distinct deliveries with shared preprocessing and honest item states. | AC-19; `test_episode_cli_renders_distinct_eligible_clips_with_shared_ingest`, `test_episode_manifest_exposes_partial_failure_and_no_clip_outcome` |
| [ ] T15 | T14 | Restart/duplicate submission preserve verified work and publish once. | AC-20; `test_restart_at_each_artifact_boundary_preserves_verified_work`, `test_duplicate_submission_cannot_duplicate_public_delivery` |
| [ ] T16 | T15 | Unknown billed outcomes and retries remain persisted, bounded and explicit. | AC-21; `test_unknown_billed_outcome_is_not_blindly_retried`, `test_retry_budget_survives_process_restart` |
| [ ] T17 | T16 | Real process/storage/runtime faults preserve primary reasons, cleanup and delivery integrity. | AC-22; `test_fault_matrix_preserves_failure_reason_and_no_false_delivery` |
| [ ] T18 | T17 | Relevant changes invalidate only dependent artifacts; schema/release rollback works. | AC-23; `test_dependency_change_invalidates_only_dependent_artifacts`, `test_previous_schema_migration_and_release_rollback_preserve_evidence` |
| [ ] T19 | T18 + labels/budgets | Independent holdout, blind comparisons, current gate/CI and owner review produce a scoped acceptance report. | AC-24; `test_acceptance_requires_current_evidence_and_reports_insufficient_sample`; every human/real-media bar in `plan.md` |
| [ ] T20 | T19 | A fresh holdout and representative use window substantiate sustained acceptance. | AC-24; repeat protocol-integrity checks; fresh independent real-media/human evidence; no automatic rating claim |

## Task execution contract

Before each task, re-ground symbols/callers and check applicable existing specs so accepted work is not rebuilt. Add tests for every affected caller, including both revision rendering paths. Keep external APIs/filesystems/processes real in the integration tests that certify their behavior; synthetic fixtures and fakes may be used only where they do not replace the claim under test.

After each task run the exact command `bash scripts/verify.sh`. Focused diagnostics do not replace it. Run relevant real-media checks, then record the tests using `bash scripts/update-ledger.sh reliable-content-aware-pipeline <TASK> <test_name[,...]>` only if the canonical gate passed and the named tests occur in that run. Preserve required hosted CI evidence before any completion claim. Do not invent reports or pre-fill ledger evidence.

Before baseline measurement, effort and calendar estimates are unknown. Human review, external access and security/runner readiness are explicit dependencies, not implementation work that an agent may certify on the owner's behalf.
