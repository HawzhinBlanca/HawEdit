# Specification — human acceptance kits

## HK-1 — Sorani corpus identity

WHEN an ASR acceptance corpus is prepared, THE system SHALL bind every item id, contained audio
path, audio SHA-256, exact raw reference SHA-256, dialect, conditions, duration, and optional word
timings to one canonical manifest and SHALL refuse missing, changed, linked, escaping, duplicate,
or training-excluded audio.

## HK-2 — Sorani rights and approval

WHEN an ASR corpus is accepted as non-interim evidence, THE system SHALL require named ownership,
licence, consent/authorization basis, use scope, and an approval record bound to the canonical
manifest digest; absence of these human assertions SHALL remain a refusal.

## HK-3 — Sorani benchmark handoff

WHEN the Sorani kit validates, THE system SHALL emit the exact benchmark command and coverage
report required by AC-7 without rewriting the raw references or silently filling missing labels.

## HK-4 — editorial sample and blinding

WHEN an editorial labelling packet is generated, THE system SHALL deterministically select 200–500
real candidates, preserve Path A/Path B provenance, assign concealed A/B presentation order without
changing verdict identity, and bind candidate media and metadata bytes.

## HK-5 — editorial labels and holdout

WHEN editorial labels are imported, THE system SHALL require independent reviewer judgments,
record disagreement and named adjudication, preserve a predeclared deterministic train/holdout
split, refuse leakage or post-label split changes, tune only on training items, and evaluate the
locked holdout with all AC-8 metrics.

## HK-6 — diarization and reframing evidence

WHEN a speaker-aware acceptance set is prepared, THE system SHALL bind authorised multi-speaker
media, exclusive reference turns, aligned reference words, gated model/revision/licence identity,
and face/crop reference evidence; the report SHALL include DER, boundary error, association errors,
crop stability, and whether output was speaker-tracked or an explicit fallback.

## HK-7 — confidential Vertex acceptance

WHEN a Vertex acceptance packet is run, THE system SHALL verify the approved project, location,
billing, ADC, zero-data-retention policy, and exact authorised media/transcript before transport;
it SHALL issue at most one bounded paid request and write a redacted, content-bound result containing
no token, credential, full transcript, or raw client frame.

## HK-8 — decision packets

WHEN an unresolved semantic choice blocks acceptance, THE system SHALL generate a stable packet
that cites the governing blueprint/blocker, measured evidence, viable options, consequences, and a
recommended option while leaving the owner decision unset.

## HK-9 — release approval packet

WHEN a production candidate is ready, THE system SHALL identify one exact protected-main SHA,
proposed version/tag, required checks, release payload hashes, attestation-verification command,
forward-only rollback procedure, residual risks, and an unset owner approval line.

## HK-10 — honesty boundary

WHEN any human assertion, licensed asset, gated access, cloud approval, expert label, or signature
is absent, THE corresponding kit SHALL remain incomplete and SHALL NOT convert synthetic fixtures,
AI-generated labels, test success, or a manifest digest into human acceptance.
