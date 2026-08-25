# Strict Stage 1 evidence — acceptance criteria

- WHEN a raw transcript contains boolean, negative, reversed or non-integer media-clock bounds,
  THE system SHALL refuse it before Stage 1 routing or artifact publication.
- WHEN confidence evidence is boolean, non-numeric, non-finite or positive,
  THE system SHALL refuse it before quartile selection.
- WHEN an ASR failure reason is empty, multiline, non-printable or larger than the producer's
  1,024-character bound, THE system SHALL refuse it rather than serialize it into a report.
- WHEN raw or normalized transcript JSON has a non-object top level, duplicate keys,
  non-standard numeric constants, non-array collections, or non-object members,
  THE system SHALL raise a bounded validation error rather than accept or leak a parser exception.
- WHEN a canonical transcript produced by HawEdit is serialized and restored,
  THE system SHALL preserve it exactly.
- WHEN valid finite Stage 1 confidence evidence reaches `SegmentScore`,
  THE system SHALL preserve the existing §3 bottom-quartile and disagreement decisions.

Approved-by: Hawa — 2026-08-17 (inherited from the explicit autonomy-first request to implement
all non-human work at maximum rigor before requesting credentials, data or decisions)
