# Plan — WSL runtime-root override

Research: `specs/wsl-runtime-root-override/research.md`

Specification: `specs/wsl-runtime-root-override/spec.md`

Impact map: `specs/wsl-runtime-root-override/impact-map.md`

Approved-by: Hawa — 2026-08-15 (inherited from the approved true-10/10 Phase 2/4 plan)

1. Add failing tests for root precedence and fail-closed invalid configuration.
2. Implement one shared, side-effect-free runtime-root resolver.
3. Route setup CLI and the canonical WSL producer through that resolver.
4. Extend the PowerShell wrapper with an exact optional root argument and a source contract test.
5. Run focused tests, Ruff, strict mypy, formatting, and the full canonical gate.
6. Use a D: external runtime root to provision the exact current-source receipt and run the live
   receipt/VEX probes; record only measurements that actually complete.
7. Update living evidence, commit explicit paths, push a draft PR, and require hosted checks before
   promotion.
