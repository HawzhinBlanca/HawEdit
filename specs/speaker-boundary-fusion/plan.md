# Plan — speaker-boundary-fusion

Research: `specs/speaker-boundary-fusion/research.md`

Specification: `specs/speaker-boundary-fusion/spec.md`

Impact map: `specs/speaker-boundary-fusion/impact-map.md`

Approved-by: Hawa — 2026-08-15 (true-10/10 plan Phase 5)

## Task 1 — strict producer seam

1. Add failing tests for valid, absent, operationally failed, overlapping, out-of-range, and
   schema-invalid diarization.
2. Implement `Diarizer`, `DiarizationUnavailable`, and pure attachment/validation.
3. Preserve existing base ingest and JSON compatibility.
4. Run focused tests, lint, format, and strict type checking.

## Task 2 — Stage 5 fusion and honest completion

1. Add failing pure tests for anchor-to-turn selection.
2. Add the structured diarization stage to `PipelineRun` and pass valid turn bounds to
   `BoundaryInputs`.
3. Prove operational failures retain base ingest and serialize without traceback.
4. Prove a run without successful diarization cannot claim completeness.
5. Run the canonical gate.

## Task 3 — promotion and next boundary

1. Update the ledger only after the canonical gate passes and only for claims evidenced by named
   tests.
2. Commit explicit paths, push the feature branch, and require hosted checks at the exact SHA.
3. Do not mark AC-9 complete. The production adapter, authenticated weights, DER/crop benchmark,
   speaker-face association, and Kurdish-editor review remain separate acceptance tasks.

