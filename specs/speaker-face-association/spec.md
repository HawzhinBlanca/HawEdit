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
