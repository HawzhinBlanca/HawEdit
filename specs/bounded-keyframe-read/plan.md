# Plan - bounded Stage 4 keyframe reads

Research: `research.md`

Specification: `spec.md`

Impact map: `impact-map.md`

Approved-by: Hawa - 2026-08-15 (inherited from approved true-10/10 Phase 8)

1. Add red tests proving the file read is capped at `ceiling + 1`, exact-ceiling input is accepted,
   and oversize or empty ffmpeg artifacts are normalized and cleaned.
2. Define one exported frame-byte ceiling in `hawedit.judge` and use it at both construction and
   extraction boundaries.
3. Preserve existing error causes and private-directory cleanup semantics.
4. Run focused and adjacent tests, static checks, the canonical gate, source-bound WSL/VEX
   acceptance, then publish through explicit commits and required hosted checks.
