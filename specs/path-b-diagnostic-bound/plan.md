# Plan — bounded Path B refusal diagnostics

Research: `specs/path-b-diagnostic-bound/research.md`

Specification: `specs/path-b-diagnostic-bound/spec.md`

Impact map: `specs/path-b-diagnostic-bound/impact-map.md`

Approved-by: Hawa — 2026-08-15 (inherited from approved true-10/10 Phase 8)

1. Add failing record-level tests for type, controls, whitespace, maximum length and tail removal.
2. Add a failing `VideoChat3Reader.read_scenes` regression through the real refusal path.
3. Implement the invariant once at `UnreadableScene` construction.
4. Run focused Path B/reader/composer/pipeline tests, Ruff, format and strict mypy.
5. Rebind the source-bound WSL VEX applicability to the exact reviewed package digest.
6. Provision the exact source receipt, run the live VEX gate, run the canonical full gate, and
   commit only explicit paths.
7. Push a draft PR and require exact hosted checks before protected promotion.
