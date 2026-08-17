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
