# Plan — credential header preflight

Research: `research.md`

Specification: `spec.md`

Impact map: `impact-map.md`

Approved-by: Hawa — 2026-08-15 (inherited from approved true-10/10 Phase 8)

1. Add direct and end-to-end CLI regressions that reproduce the header exception and secret leak.
2. Refuse only values unsafe for an HTTP header, before calling the injected/default transport;
   keep live API validation authoritative for safe values.
3. Rebind the WSL VEX source applicability, run focused security/CLI suites, strict static checks,
   and the canonical gate.
4. Record evidence and publish only through explicit commits and green hosted checks.

