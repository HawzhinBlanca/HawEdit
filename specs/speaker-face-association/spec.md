# Specification — speaker/face association

## Acceptance criteria

- **AC-1:** WHEN a speaker-aware tracker is enabled, THE pipeline SHALL provide only exclusive
  diarization turns that overlap the final clip.
- **AC-2:** WHEN a speaker-aware tracker returns a point, THE pipeline SHALL require exact integer
  media-clock coordinates, strict chronological order, clip containment, and a speaker label equal
  to the exclusive turn active at that instant.
- **AC-3:** WHEN at least one valid speaker-labelled point is returned, THE clip SHALL record
  `crop_target=speaker_face` and THE render artifact SHALL record `Reframe.SPEAKER_TRACKED`.
- **AC-4:** WHEN the speaker-aware result is empty, THE pipeline SHALL treat it as explicit
  ambiguity and fall back to the requested face-only tracker, or static centre when none exists.
- **AC-5:** WHEN speaker association fails operationally or returns invalid evidence, THE pipeline
  SHALL emit a structured render-stage refusal and SHALL NOT silently use the ambiguity fallback.
- **AC-6:** WHEN speaker association is requested without measured diarization or without an
  overlapping turn, THE pipeline SHALL refuse that requested mode explicitly.
- **AC-7:** WHEN render receives points and an explicit reframe mode, THE renderer SHALL refuse a
  static mode with dynamic points, a dynamic mode without points, or any unsupported mode.
- **AC-8:** WHEN no speaker-aware tracker is supplied, THE existing face-tracked/static-centre
  behavior and artifact labels SHALL remain unchanged.
- **AC-9:** WHEN the production pyannote repository, associator, and labelled multi-speaker footage
  are absent, THE project SHALL retain PARTIAL/BLOCKED status and SHALL NOT claim active-speaker
  accuracy or production completeness.

## Current Production Admission Extension (Approved Phase 5)

Historical AC-3/AC-4 describe structural point presence and preview behavior.
They do not authorize a production crop from unknown/listener evidence; current
production refusal policy and the following stronger criteria apply.

- **AC-10:** WHEN no usable speaking observation establishes a camera, THE
  layout policy SHALL NOT seed a camera from a listener, off-screen, unknown,
  non-speaking or below-policy-confidence observation.
  Tests: `test_layout_policy_refuses_unestablished_camera_evidence`.
- **AC-11:** WHEN a shot cut resets spatial continuity, ambiguous observations
  are returned in that shot and none establishes usable speaking evidence,
  THE layout policy SHALL refuse the ungrounded
  camera rather than reuse a pre-cut location or seed the observed listener.
  Tests: `test_layout_policy_refuses_ambiguous_post_cut_seed`.
- **AC-12:** WHEN requested production speaker association has no usable layout,
  THE single-clip and episode routes SHALL record a render refusal without a
  substituted crop or rendered review video.
  Tests: `test_production_rejects_non_speaking_camera_evidence_in_both_routes`.
- **AC-13:** WHEN split positions are derived from speaker observations, THE
  camera resolver SHALL exclude listener/non-speaking/below-policy-confidence
  observations while retaining the structural observation record.
  Tests: `test_split_centres_ignore_non_speaking_observations_in_both_routes`.
- **AC-14:** WHEN ambiguous evidence follows a confirmed camera in the same
  shot, THE layout policy SHALL preserve the existing established hold policy;
  WHEN structural validation receives a valid listener observation, THE
  validator SHALL retain it without asserting usable speaker evidence.
  Tests: `test_layout_policy_holds_on_ambiguity_and_switches_on_verified_turn`,
  `test_structural_listener_validation_does_not_assert_camera_admission`.
- **AC-15:** WHEN early observations are ambiguous but usable speaking evidence
  later establishes a camera within the same shot, THE layout policy SHALL
  derive its first keyframe only from that usable observation, not from the
  ambiguous location. This is camera evidence admission, not an assertion of
  frame-by-frame identity accuracy.
  Tests: `test_layout_policy_seeds_from_first_verified_observation`.

These names are planned regressions, not passing evidence or accuracy claims.

- **AC-16:** WHEN either rendering route promotes a measured MP4 into its
  private review bundle, THE returned render path SHALL name those existing
  measured bytes and SHALL NOT retain the departed staging path or assert
  publication/completion.
  Test: `test_review_render_path_names_the_measured_private_bytes_in_both_routes`.
