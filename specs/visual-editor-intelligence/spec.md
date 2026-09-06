# Proposed acceptance criteria — visual editorial intelligence

These are EARS requirements for the new extension. Tests are proposed names, not existing passing evidence. Reuse the original reliability criteria where indicated in `plan.md`; do not duplicate ledger credit. Every visually observable claim also needs the labelled real-media evidence and human review specified there.

| ID / unit | Requirement | Proposed automated test |
|---|---|---|
| VE-00 / V00 | WHEN a required visual-measurement dependency is unavailable or an approved file/sidecar binding changes, THE system SHALL return explicit failure/unknown and refuse dependent publication, never fabricate a success value. | `test_missing_visual_measurement_dependency_never_reports_success`, `test_promotion_rejects_changed_sidecar_or_plan_binding` |
| VE-01 / V01 | WHEN an edit plan is resolved or replayed, THE system SHALL derive every output artifact and event from the same immutable source-time mapping and effective configuration. | `test_visual_plan_replay_preserves_all_artifact_timebases` |
| VE-02 / V02 | WHEN an episode is scanned, THE system SHALL inventory observation coverage for all source intervals and distinguish sampled/model-inspected/unknown evidence without suppressing static verbal moments. | `test_observation_inventory_exposes_unseen_intervals_and_static_speech` |
| VE-03 / V03 | WHEN an important event is uncertain or falls between coarse samples, THE system SHALL request bounded targeted observation or declare insufficient evidence, while preserving configured model/frame/pixel budgets. | `test_targeted_visual_observation_respects_budget_and_recovers_brief_event` |
| VE-04 / V04 | WHEN visible identity, speaking identity or shot continuity is uncertain, THE system SHALL avoid unsupported association and explicitly represent listener/off-screen/unknown states. | `test_visual_identity_does_not_equate_lone_face_with_active_voice` |
| VE-05 / V05 | WHEN a story relation is proposed, THE system SHALL validate its canonical sentence and visual-event references and preserve the distinction between source assertion, observation and editorial interpretation. | `test_story_relations_require_canonical_and_visual_evidence` |
| VE-06 / V06 | WHEN a candidate omits necessary question, qualification or payoff, THE system SHALL expand within approved contiguous-source constraints or reject it before ranking. | `test_visual_candidate_keeps_required_context_and_landing_beat` |
| VE-07 / V07 | WHEN an output shot is planned, THE system SHALL require an editorial purpose, supporting source evidence, protected-content regions and a valid source-to-output interval. | `test_every_planned_shot_has_source_evidence_and_protected_regions` |
| VE-08 / V08 | WHEN crop/layout decisions span a shot, THE system SHALL preserve required visible content with an approved stable camera path or choose an explicit source-preserving alternative. | `test_shot_composition_preserves_required_content_without_crop_jitter` |
| VE-09 / V09 | WHEN timing is tightened or a reaction is selected, THE system SHALL preserve complete speech, protected pauses and the source's relevant temporal/causal relationships. | `test_edit_cannot_fabricate_reaction_timing_or_cut_protected_pause` |
| VE-10 / V10 | WHEN captions overlap essential visual content or overflow readable geometry, THE system SHALL reposition/regroup them within approved constraints or request review without altering canonical speech. | `test_caption_layout_avoids_essential_visual_regions_without_text_changes` |
| VE-11 / V11 | WHEN a private render is ready, THE system SHALL inspect its actual temporal output and source context, report timestamped grounded defects and refuse unsupported all-clear claims. | `test_render_critic_uses_output_sequence_and_reports_grounded_defects` |
| VE-12 / V12 | WHEN a repair is proposed, THE system SHALL allow only approved transformations, invalidate prior review, enforce cumulative iteration/cost limits and stop on non-improvement or oscillation. | `test_visual_repair_is_bounded_and_cannot_change_meaning_or_approve_itself` |
| VE-13 / V13 | WHEN an episode requests N clips, THE system SHALL share preprocessing and return up to N distinct eligible, independently checked candidates with truthful per-item states. | `test_episode_visual_delivery_shares_preprocessing_and_reports_each_state` |
| VE-14 / V14 | WHEN execution crashes, retries or resumes after an uncertain external outcome, THE system SHALL preserve verified evidence, resource ownership and publication idempotency without claiming exactly-once external billing. | `test_visual_workflow_recovery_preserves_evidence_and_publication_identity` |
| VE-15 / V15 | WHEN a release scorecard is produced, THE system SHALL require current evidence, account for all proposals/refusals and episode clustering, exclude leaked holdouts and refuse unsupported leadership claims. | `test_visual_scorecard_requires_unseen_current_evidence_and_full_accounting` |

## What each test must prove

- Pure policy tests may use constructed metadata. Rendering/measurement tests must use real decoded media where the claim is about pixels, audio or timing.
- Dependency absence and process/storage/network faults may be deliberately injected. Do not mock the detector, renderer or critique output in a test that claims to prove its accuracy.
- Use deliberately damaged outputs to challenge the verifier: no captions on textured footage, different text with identical geometry, source nameplate mistaken for captions, cropped demonstration, incorrect listener identity, misplaced reaction, missing caveat and wrong sidecar clocks.
- Automated critique tests can validate data flow, budgets, schemas and seeded-defect handling. Human labels on natural footage remain necessary to establish editorial accuracy and useful repair rate.
- Include counterexamples: a quiet long take can be excellent; a listener shot can be the right editorial choice; a meaningful pause is not an error; a preserved wide shot may be necessary to show the subject.
- Gate acceptance is the exact `bash scripts/verify.sh` plus applicable real-media and required exact-SHA hosted checks. Do not alter the tests to make the current output appear correct.

## Human judgement rubric

Reviewers answer independently before adjudication: Does the clip mean the same thing as the original passage? Is necessary context present? Does each shot preserve the relevant visual information? Are reactions and events represented honestly? Does the sequence flow? Are captions readable and accurate? Is any correction required before publication? If more than one edit is acceptable, record the acceptable alternatives and preference rather than manufacture a single ground truth.
