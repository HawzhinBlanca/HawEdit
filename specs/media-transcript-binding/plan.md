# Plan — media/transcript byte identity

Research: `research.md`
Specification: `spec.md`
Impact map: `impact-map.md`

Approved-by: Hawa — 2026-08-17 (inherited from the approved autonomy-first true-10/10 execution request)

1. Add failing schema/unit tests for strict SHA-256 types, legacy parsing and render refusal.
2. Make Stage 0 expose one stable source SHA-256 and prove start/end drift refusal.
3. Bind supplied, newly produced and cached transcripts to that digest before downstream work.
4. Recheck source bytes at every source-consuming stage boundary and before bundle publication;
   preserve the existing structured operational-error contract while treating content mismatch as
   a hard integrity error.
5. Carry the digest into `Clip` and editing JSON, with a render-gate regression.
6. Run transcript/ingest/clip/render/pipeline adjacency, then the exact canonical gate. Rebind the
   source-dependent WSL/VEX receipt only after the code unit is final.
