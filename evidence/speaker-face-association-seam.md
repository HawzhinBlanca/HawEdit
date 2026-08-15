# Speaker/face association seam — 2026-08-15

This record covers the code-solvable §3 Stage 6 association boundary. It is not evidence that a
production active-speaker model is accurate or available.

## Implemented contract

- `SpeakerSubjectTracker` is a separate protocol from the existing face-only `SubjectTracker`.
- The pipeline passes it only validated exclusive diarization turns overlapping the fused final
  clip.
- Every `SpeakerFocusPoint` is an exact non-negative integer media-clock coordinate, is strictly
  chronological and inside the final clip, and names the exclusive speaker active at that instant.
- A non-empty validated result produces `crop_target=speaker_face` and
  `Reframe.SPEAKER_TRACKED` on the artifact.
- An empty result means explicit ambiguity and may fall back to face-only tracking or static
  centre. Invalid evidence, operational failure, missing diarization, or no overlapping turn is a
  structured refusal and never takes that fallback.
- `render_clip` independently refuses static provenance with dynamic points and dynamic
  provenance without points before probing or encoding.

The reviewed source package digest is
`ae89089ecbcfab1eac580671d0cd1f387618006918b33b6ce90a28e6c0001c7a`; the WSL ASR VEX
applicability policy is rebound to that exact identity without changing any advisory disposition.

## Executable evidence

On Windows, CPython 3.12.10, and the repository's verified ffmpeg 8.1.1/libass stack:

- the complete pipeline/render files passed 256/256 tests;
- the VEX/policy files passed 39/39 tests;
- the canonical gate passed 2,478/2,478 tests with zero skipped in 367.59 seconds; and
- the ledger-controlled fresh gate passed the same 2,478/2,478 with zero skipped in 370.37
  seconds and found every cited test in its own JUnit report.

Named acceptance tests:

- `test_speaker_tracking_receives_only_overlapping_turns_and_labels_the_artifact`
- `test_ambiguous_speaker_tracking_falls_back_without_claiming_speaker_provenance`
- `test_requested_speaker_tracking_refuses_missing_diarization_without_calling_provider`
- `test_invalid_or_failed_speaker_association_is_not_silently_treated_as_ambiguity`
- `test_real_render_preserves_validated_speaker_tracking_provenance`
- `test_render_refuses_a_reframe_label_that_contradicts_its_points`

## Remaining production boundary

The repository does not contain a production speaker/face associator and exposes no CLI flag that
pretends otherwise. The gated `pyannote/speaker-diarization-community-1` repository still requires
external approval (`BLOCKED.md` #4), and the checked-in media fixture contains no real faces.
Association accuracy, off-screen-speaker behavior, shot-change behavior, multi-face stability and
crop quality therefore remain unmeasured until authorised labelled multi-speaker footage and human
review are available (`BLOCKED.md` #1). M3.3 and M8.1 remain PARTIAL.
