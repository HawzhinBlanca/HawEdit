# Plan — human acceptance kits

Research: `specs/human-acceptance-kits/research.md`

Specification: `specs/human-acceptance-kits/spec.md`

Impact map: `specs/human-acceptance-kits/impact-map.md`

Approved-by: Hawa — inherited from the approved autonomy-first execution plan, 2026-08-17

## Task 1 — Sorani ASR corpus acceptance

1. Add a strict companion manifest whose canonical bytes bind the existing corpus manifest and
   every contained audio/reference item.
2. Validate safe relative paths and stable regular files; refuse symlinks/reparse points, hardlinks,
   byte drift, duplicate identities/audio, missing rights fields, incomplete §8.1 coverage, and
   declared training/exclusion collisions.
3. Emit a deterministic coverage/handoff report, canonical manifest digest, approval template, and
   exact `hawedit-asr-bench` command without copying client audio into the repository.
4. Add malformed-schema, traversal/link/race, duplicate/leakage, byte-drift, approval-binding, and
   successful real-file fixture regressions.

## Task 2 — blinded editorial study

1. Define the immutable candidate inventory and deterministic 200–500 selection rule.
2. Generate concealed A/B packets and reviewer forms without exposing model identity.
3. Import independent labels, preserve disagreements/adjudication, freeze train/holdout before
   tuning, and produce the complete AC-8 report using existing metrics.
4. Prove ordering, split, bytes, and labels cannot be silently changed or reused across studies.

## Task 3 — diarization/reframe acceptance

1. Define and verify the multi-speaker media/reference manifest and gated-model receipt.
2. Compose existing DER/boundary metrics with active-speaker association and crop-stability metrics.
3. Produce an explicit speaker-tracked/fallback acceptance result and attribution packet.

## Task 4 — Vertex and decision kits

1. Add a no-transport Vertex preflight and one-request redacted evidence writer.
2. Generate evidence-backed, unset decision packets for #13/#14/#15/#18/#9/#21.

## Task 5 — release and integrated handoff

1. Generate the exact-SHA version/tag/attestation/rollback approval packet.
2. Package stable templates and add an installed CLI only after the library formats are settled.
3. Run focused checks and the canonical gate after every bounded task; update the acceptance task
   ledger only after exact-SHA hosted checks meet the governing rule.

No task may mark human approval complete. The autonomous exit is a set of verified, ready-to-fill
packets and commands that require no further engineering discovery when the human inputs arrive.
