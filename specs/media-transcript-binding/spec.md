# Specification — media/transcript byte identity

Parent acceptance: true-10/10 AC-1, AC-9 and AC-12; BLUEPRINT §§1–5.

## Acceptance criteria

1. WHEN Stage 0 accepts a source, THE ingest result SHALL carry a lowercase SHA-256 of the exact
   source bytes and SHALL refuse if those bytes change during Stage 0.
2. WHEN a transcript is supplied to the runner, THE runner SHALL require its media SHA-256 to
   equal Stage 0's source SHA-256 before discovery, judging or rendering.
3. WHEN canonical ASR produces a transcript, THE runner SHALL bind it to Stage 0's exact source
   SHA-256 before write-once publication.
4. WHEN Stage 1 considers cached output, THE transcript store SHALL reuse it only when audio,
   producer and media SHA-256 all match the current run.
5. WHEN a pixel-consuming stage starts and finishes, THE runner SHALL verify that the source still
   has Stage 0's SHA-256; drift SHALL refuse before a billed judgment or public delivery.
6. WHEN a clip is rendered or serialized as editing JSON, THE clip SHALL carry the exact lowercase
   source SHA-256; a legacy/unbound clip SHALL remain readable but SHALL NOT render.
7. WHEN legacy transcript/clip JSON lacks the new field, THE parser SHALL preserve read access as
   an explicitly unbound value and SHALL NOT silently invent identity.
