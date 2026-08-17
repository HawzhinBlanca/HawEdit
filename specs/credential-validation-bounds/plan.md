# Plan — credential validation response bounds

Research: `research.md`

Specification: `spec.md`

Impact map: `impact-map.md`

Approved-by: Hawa — 2026-08-15 (inherited from approved true-10/10 Phase 8)

1. Add failing regressions for an echoed key, controls, oversized diagnostic, and a response stream
   that must not be read without a byte limit.
2. Centralize bounded printable redaction at the validation boundary and use a bounded stream read
   for both success and HTTP-error responses.
3. Run the focused credential/Gemini/CLI suites, strict lint/type checks, then the canonical gate.
4. Record exact evidence and publish through explicit paths only after the gate is green.

