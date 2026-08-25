# Strict Stage 1 evidence — implementation plan

1. Add failing constructor and JSON-boundary tests for the reproduced boolean/NaN cases.
2. Add small private validators for exact integer milliseconds, finite log-probabilities and
   bounded printable one-line reasons; use them in all persisted Stage 1 evidence dataclasses.
3. Replace permissive transcript JSON decoding with duplicate-safe, non-standard-number-safe,
   shape-checked decoding while retaining documented legacy optional fields.
4. Apply the same confidence contract to `SegmentScore` and preserve valid routing semantics.
5. Add a CLI regression proving malformed supplied evidence exits 2 without traceback/output
   contamination.
6. Run focused tests, Ruff, formatting, strict mypy, then the exact canonical gate.
7. Only after a green gate, update the ledger/evidence if this closes a documented row; otherwise
   record it as a hardening amendment without changing milestone status.
