# Plan — no authentication redirects

Research: `research.md`

Specification: `spec.md`

Impact map: `impact-map.md`

Approved-by: Hawa — 2026-08-15 (inherited from approved true-10/10 Phase 8)

1. Add a real loopback redirect regression that records whether either fake authentication header
   reaches the target.
2. Centralize a no-redirect stdlib opener and route both credential and Gemini/Vertex transports
   through it; keep unauthenticated asset download semantics unchanged.
3. Migrate response-bound mocks to the shared seam and run credential/Gemini/pipeline/release
   adjacency plus strict static checks.
4. Rebind source VEX applicability, run canonical gate and live VEX, record evidence, and publish
   through explicit commits plus green hosted checks.
