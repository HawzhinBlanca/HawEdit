# Tasks ledger — face-probe-height-floor
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [ ] T1  ADR D-335; 5 % height floor in the delivery face probe   (tests: test_a_detection_below_the_height_floor_is_not_a_face, test_a_detection_at_the_height_floor_is_a_face, test_an_undersized_frontal_box_does_not_stop_the_profile_fallback)
- [ ] T2  A faceless face_tracked render is refused; BLOCKED #26 resolved   (tests: test_ambiguous_speaker_tracking_falls_back_without_claiming_speaker_provenance)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
