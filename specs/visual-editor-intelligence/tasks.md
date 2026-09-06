# Task sequence — visual editor intelligence

Approved-by: pending for new visual-intelligence extensions; existing authorization in `../reliable-content-aware-pipeline/plan.md` is preserved.

Every row is proposed and unchecked. Read the linked specification for full EARS requirements. Named tests are planned tests, not present/green evidence. A row is accepted only after the canonical gate, required media evidence and exact-SHA required CI; only `scripts/update-ledger.sh` may flip rows.

- [x] V00 Close remaining false-success paths and enforce caption/sidecar integrity
- [x] V01 Establish one source clock and one edit contract
- [x] V02 Inventory the entire episode's visual evidence
- [x] V03 Inspect uncertain visual events more closely
- [x] V04 Distinguish people, speakers, listeners and off-screen speech
- [x] V05 Connect story meaning to visual events
- [x] V06 Select complete ideas with setup and payoff
- [x] V07 Plan every shot with an editorial purpose
- [ ] V08 Compose across whole shots without crop jitter
- [ ] V09 Protect continuity, meaningful pauses and reaction timing
- [ ] V10 Make captions support the picture and avoid essential regions
- [ ] V11 Inspect the actual rendered sequence with post-render critique
- [ ] V12 Repair specific defects within bounded iterations
- [ ] V13 Produce a coherent episode package with shared preprocessing
- [ ] V14 Prove recovery, idempotency and maintainability
- [ ] V15 Earn the ranking independently with holdout evaluation

| Task | Dependency | Smallest observable outcome | Criteria / proposed test evidence |
|---|---|---|---|
| [ ] V00 | Baseline | Close false-success paths, enforce caption integrity and sidecar plan binding. | VE-00; `test_missing_visual_measurement_dependency_never_reports_success`, `test_promotion_rejects_changed_sidecar_or_plan_binding` |
| [ ] V01 | V00 | One source clock and one edit contract driving all exports. | VE-01; `test_visual_plan_replay_preserves_all_artifact_timebases` |
| [ ] V02 | V01 | Inventory observation coverage for all source intervals. | VE-02; `test_observation_inventory_exposes_unseen_intervals_and_static_speech` |
| [ ] V03 | V02 | Targeted visual observation around key moments respecting budgets. | VE-03; `test_targeted_visual_observation_respects_budget_and_recovers_brief_event` |
| [ ] V04 | V03 | Distinguish people, speakers, listeners and off-screen speech. | VE-04; `test_visual_identity_does_not_equate_lone_face_with_active_voice` |
| [ ] V05 | V04 | Connect story meaning to visual events and canonical sentences. | VE-05; `test_story_relations_require_canonical_and_visual_evidence` |
| [ ] V06 | V05 | Select complete ideas preserving setup and landing beat. | VE-06; `test_visual_candidate_keeps_required_context_and_landing_beat` |
| [ ] V07 | V06 | Plan every shot with an editorial purpose and protected regions. | VE-07; `test_every_planned_shot_has_source_evidence_and_protected_regions` |
| [ ] V08 | V07 | Compose across whole shots without crop jitter. | VE-08; `test_shot_composition_preserves_required_content_without_crop_jitter` |
| [ ] V09 | V08 | Protect continuity, meaningful pauses and reaction timing. | VE-09; `test_edit_cannot_fabricate_reaction_timing_or_cut_protected_pause` |
| [ ] V10 | V09 | Make captions avoid essential visual regions without text drift. | VE-10; `test_caption_layout_avoids_essential_visual_regions_without_text_changes` |
| [ ] V11 | V10 | Inspect actual rendered sequence with post-render critic. | VE-11; `test_render_critic_uses_output_sequence_and_reports_grounded_defects` |
| [ ] V12 | V11 | Bounded iterative repair of specific detected defects. | VE-12; `test_visual_repair_is_bounded_and_cannot_change_meaning_or_approve_itself` |
| [ ] V13 | V12 | Episode package with shared preprocessing and distinct candidates. | VE-13; `test_episode_visual_delivery_shares_preprocessing_and_reports_each_state` |
| [ ] V14 | V13 | Workflow recovery, evidence preservation and idempotent publication. | VE-14; `test_visual_workflow_recovery_preserves_evidence_and_publication_identity` |
| [ ] V15 | V14 | Holdout evaluation and independent competitive benchmark. | VE-15; `test_visual_scorecard_requires_unseen_current_evidence_and_full_accounting` |
