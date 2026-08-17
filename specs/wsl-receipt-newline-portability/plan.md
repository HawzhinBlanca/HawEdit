# Plan — WSL receipt newline portability

Research: `specs/wsl-receipt-newline-portability/research.md`

Specification: `specs/wsl-receipt-newline-portability/spec.md`

Impact map: `specs/wsl-receipt-newline-portability/impact-map.md`

Approved-by: Hawa — inherited from the approved `specs/true-10-10-acceptance/plan.md`

1. Add a failing regression that publishes CRLF source/metadata and validates it from an LF
   materialization of the same content.
2. Reuse one universal-newline canonicalizer in the source digest and metadata equivalence check.
3. Prove semantically changed metadata still refuses and retain all structural/link/stability gates.
4. Run the focused suite, then the canonical local gate.
5. Commit explicit paths, obtain clean pull-request checks, merge, reprovision the receipt for the
   merged source digest, and rerun the exact-main WSL/hosted gate.
