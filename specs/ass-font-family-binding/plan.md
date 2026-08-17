# Plan — ASS font-family binding

Research: `research.md`

Specification: `spec.md`

Impact map: `impact-map.md`

Approved-by: Hawa — 2026-08-15 (inherited from approved true-10/10 Phase 8)

1. Add adversarial tests showing a covering unrelated font cannot certify the requested family,
   plus missing/undefined/malformed/override refusals and the shipped positive control.
2. Parse the used ASS styles at the render boundary, resolve only authoritative font family names
   from regular files in `fonts_dir`, and check Kurdish coverage on the matched font itself.
3. Route `render_clip` through the ASS-aware guard using the same decoded ASS text as the timing
   check; preserve the directory-only helper for its explicit direct API.
4. Run caption/render/pipeline/release adjacency, canonical gate, source-bound WSL/VEX acceptance,
   and publish through explicit commits plus green hosted checks.
