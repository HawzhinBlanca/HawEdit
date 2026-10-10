# Legacy Camera Test Contract Research

2026-10-10. Parent: approved evidence-based Phase5 and speaker-face-association
AC-10 through AC-16; BLUEPRINT §3 Stage6 and §§8.1-8.3, D-241/D-263/D-274.
No implementation of this extension yet.

The actual affected cohort has573pass/1fail/0errors/skips across574cases,
JUnit672.275s. Failure: the existing
test_pipeline_integrates_motion_speaker_tracker_for_active_speaker_reframe
expects speaker_face/SPEAKER_TRACKED with a digit fixture and injected Haar
boxes, without usable speaking evidence admitted by the repaired layout.
The default preview correctly reports static_centre instead. Its private
artifact contains boundary0..1950ms; actual source cuts are1400/2800ms.
These are contract observations, not real-person identity measurements.

Original test, detector inputs, QC helper/digest and fixture remain unchanged.
tests/test_pipeline.py SHA256
eac8117a04d37ed092aa6ad581320a28fbf80f8362fcfd879ebda754f0ddc200.
Raw affected report:
C:/Users/Wareen/HawEdit-video-rating-20261010/camera-admission-affected.xml,
SHA25631aad365c24d07ba5830818e54aed77a7ec5a4e771129c5c3c4de73de97ae3a8.
Original failed artifacts preserved in legacy-motion-conflict-artifacts under
that evidence root. Do not alter a QC digest, fixture or golden to fit output.

Actual installed Serena/LSP five-pair map, baseline9a7c8169bdd2f005177d52050aec5f68c2edd578
with explicitly dirty camera patch, unchanged=true:
C:/Users/Wareen/HawEditLegacyCameraContractMap-20261010/serena-map.json,
SHA25647da35e0bdfb3472d233809495f69ea766f9d6c9f895e6e54a933a9a84e87597.
It maps the test, _test_qc, MOTION_SPEAKER_TRACKED_RENDER_SHA256,
MotionSpeakerTracker.track_speakers and _resolve_camera. Definition/reference
results are raw authoritative evidence; dynamic protocol calls are additionally
exercised by both actual render routes.

Proposed correction is a stronger test contract: establish the real tracker's
lack of admitted speaking evidence; assert explicitly unverified private preview
behavior and production refusal without an MP4. Retain the source fixture,
detector inputs, thresholds, signatures, digest constant and original red report.
Do not change source behavior to fabricate a speaker. Preserve existing genuine
known-observation positive render controls and synthetic-motion algorithm tests.
Those positives are not native-editor identity acceptance.

This conflicts with the earlier unit's literal promise to leave every old
assertion untouched; request owner approval before correcting this expectation.
No skipped/deselected case, weakened claim, gate override or evidence renewal.
Independent current-package VEX (#24), same-SHA CI/runner (#25), native identity
and editorial acceptance remain required regardless of a corrected local test.
