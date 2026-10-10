# Plan — speaker/face association

Research: `specs/speaker-face-association/research.md`

Specification: `specs/speaker-face-association/spec.md`

Impact map: `specs/speaker-face-association/impact-map.md`

Approved-by: Hawa — 2026-08-15 (inherited from approved true-10/10 Phase 5)

1. Add failing unit tests for strict speaker-labelled focus evidence and turn reconciliation.
2. Implement the separate speaker-aware protocol and validator without changing face-only callers.
3. Add failing pipeline tests for success, ambiguity fallback, missing diarization, and invalid or
   operational tracker output.
4. Compose overlapping turns into Stage 6 and derive one explicit reframe mode/crop target.
5. Add renderer tests and explicit mode/point consistency enforcement.
6. Run focused tests, Ruff, strict mypy, and formatting.
7. Update evidence/living docs honestly; rebind the WSL VEX source digest because source changed.
8. Commit explicit paths, run the clean full canonical gate, ratchet only through the gate, push a
   draft PR, and require hosted checks before promotion.

## Current Execution Clarification (2026-10-10)

This follow-up implements the existing approved Phase 5 meaning/speaker fidelity
obligation and current owner output-quality goal, not a new runtime architecture.
Research and actual seven-pair Serena caller map precede edits. Implement AC-10
through AC-15 as one sequential test-first unit: add red controls, repair only
layout seed/admission and split aggregation, preserve structural callers, run
whole affected cohorts and exact `bash scripts/verify.sh`, then preserve current
SHA evidence. Rows remain WIP without green gate and applicable same-SHA CI.

Step 7's historical self-rebinding instruction is explicitly superseded:
qualified independent current-package security review (#24) is required. Never
self-rebind/renew VEX. Prior promotion/check marks do not cover this follow-up.
No push, publication, new installation, model change, cloud media sharing or
native speaker-accuracy claim is authorized by this clarification.
