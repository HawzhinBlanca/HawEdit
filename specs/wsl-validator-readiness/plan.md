# Plan — WSL validator readiness

Research: `specs/wsl-validator-readiness/research.md`

Specification: `specs/wsl-validator-readiness/spec.md`

Impact map: `specs/wsl-validator-readiness/impact-map.md`

Approved-by: Hawa — 2026-08-15 (inherited from the approved true-10/10 execution plan)

1. Add failing status, missing-byte, fetch-plan, runtime-cache, and WSL producer tests for AC-1
   through AC-8.
2. Factor exact-byte readiness from complete component readiness in `ModelStore`.
3. Route the Windows rzgar status through the existing cached canonical WSL proof while preserving
   non-Windows and generic loader behavior.
4. Retain and regression-test the WSL producer's single exact verification and full-subprocess
   lease; do not add a redundant 10.1 GB pre-hash.
5. Run focused tests, Ruff, formatting, strict mypy, and the full canonical gate.
6. Update the living evidence/ledger only from the successful gate; commit explicit paths, push a
   PR, and require exact-SHA hosted checks before merge.
7. Reprovision the source-bound WSL receipt after merge and repeat live VEX plus long-form Stage 1
   acceptance before carrying the new SHA into visual acceptance.
