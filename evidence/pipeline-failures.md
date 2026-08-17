# Structured operational failures - 2026-08-09

## Reproduced failures

Expected missing-model, ffmpeg, Gemini credential, Vertex ADC, inference and tracker failures could
escape the runner as raw exceptions. Auto-selection could call Stage 4 even when no complete
sentence was selectable. An injected candidate ID could traverse outside the work directory.
Backend messages and keyframe-cleanup notes could also enter JSON with control characters or a
million-byte credential-shaped tail.

## Enforced boundary

`run_pipeline` converts only named operational adapter errors into the affected stage's
`StageSkipped`; assertions, invalid persisted verdicts and unlisted exceptions still raise.
Operational model and credential acquisition is lazy so the runner exists before it fails, while
static routing/governance remains eager. A selection with no complete sentence returns before
keyframe extraction/judging. Candidate identifiers must map to one safe path component before any
filesystem use.

Every exception-derived skip reason is printable, whitespace-normalized and hard-bounded. The base
message has its own 1,024-character cap; at most four cleanup notes share a separate 512-character
budget. Ordinary short one-line messages stay exact. Credential-file/ADC I/O failures send zero
requests and become `GeminiUnavailable`; arbitrary assertion controls are not swallowed.
`generateContent` is attempted at most once: a reset or 5xx after upload is ambiguous and is never
replayed without a provider idempotency mechanism, preventing duplicate billing/verdicts.

## Controls

The regressions inject each named stage failure, traversal identifiers, no-anchor survivors,
missing real CLI model directories, credential permission/encoding/auth failures, cleanup notes,
control bytes and a one-million-character provider message. JSON remains parseable and bounded,
no forbidden call is made, and programmer exceptions still surface.
