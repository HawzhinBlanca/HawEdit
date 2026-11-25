# Candidate framing parity EARS

Proposed requirements, not observed passes. BLUEPRINT sections 2-5; D-263,
D-274, D-276 and D-277. This is camera admission/parity, not speaker accuracy.

| ID | Requirement | Proposed named regression |
|---|---|---|
| CF-1 | WHEN speaker tracking is requested without validated overlapping diarization, THE pipeline SHALL refuse that candidate's render identically in single and episode routes. | `test_requested_speaker_tracking_refuses_missing_turns_in_both_routes` |
| CF-2 | WHEN association fails, is invalid, or supplies no usable speaker evidence under production constraints, THE pipeline SHALL expose a bounded refusal without substituting face or centre tracking. | `test_production_association_failure_never_substitutes_a_crop` |
| CF-3 | WHEN measured association is usable, THE pipeline SHALL invoke it on the final source-bound interval and preserve validated speaker turns and resulting layout in the candidate's immutable edit plan. | `test_episode_candidate_retains_validated_speaker_camera_evidence` |
| CF-4 | WHEN split mode is explicitly requested, THE pipeline SHALL preserve that effective policy; `always` with insufficient subjects SHALL refuse, and `never` SHALL not create a split. | `test_episode_split_policy_is_executed_and_recorded_without_override` |
| CF-5 | WHEN a split layout has already been selected, THE pipeline SHALL not replace it by invoking a dominant-face path merely because its continuous focus-point list is empty. | `test_selected_split_cannot_be_overwritten_by_subject_tracker` |
| CF-6 | WHEN a production candidate's required tracking fails, THE episode orchestrator SHALL retain a refused item and no plausible deliverable or successful camera claim for that item. | `test_episode_tracking_refusal_preserves_honest_item_state` |
| CF-7 | WHEN this repair runs, THE system SHALL preserve canonical raw, source bytes, review/publication separation, timing and caption invariants, and exact-byte review binding. | `test_camera_parity_preserves_source_raw_and_private_review_contract` |
| CF-8 | WHEN more than two speakers are tracked, THE pipeline SHALL refuse a forced two-person layout and SHALL keep all speaker evidence in automatic speaker framing rather than selecting only the first two subjects. | `test_two_person_layout_never_drops_a_third_tracked_speaker` |

Tests use decoded media plus explicit failure injections for control-flow evidence.
Speaker identity accuracy needs licensed labelled audiovisual clips and independent
native review; a face-detection count, synthetic test identity or plan field is not
that evidence. No new verified publication or release rating follows from these tests.
