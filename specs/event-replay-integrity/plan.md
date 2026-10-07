# Scoped Implementation Plan

Approved-by: Wareen - explicit parent PLEASE IMPLEMENT THIS PLAN, approve all,
and2026-10-07 continue finish the job; existing T3 durable-state/refusal scope.
Local commits only. No new dependency/architecture, key enrollment, spending,
licence acceptance, VEX review, push or release approval.

1. Preserve actual Serena map, original counterexample and red baseline gate.
2. Add genuine-reader/sink/timeline tests first; preserve their expected failures.
3. Keep complete valid final records, LF/CRLF, live reads and missing-file behavior.
   Refuse malformed complete/middle records with line/evidence-preservation
   context. Tolerate only a plausible incomplete unterminated final JSON write;
   ambiguous corruption is refused. Do not alter the original bytes.
4. Correct the legacy flush-versus-fsync documentation without claiming protected
   attempt adoption. Keep projector and signed billing authority unchanged.
5. Run whole affected caller modules, fast lint/strict types and formatting.
   Freeze a reviewed local commit and run exact bash scripts/verify.sh.
6. Preserve failures, versions/hashes and final terminal evidence outside frozen
   source. No ledger promotion unless exact gate and applicable same-SHA CI pass.

Current qualified security review BLOCKED#24 and full producer/review/export,
ZAR38 fidelity and independent/sustained acceptance remain separate obligations.
