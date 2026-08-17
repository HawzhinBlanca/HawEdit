# Impact map — current acceptance records

## Files and readers

- `README.md`: setup operators choosing WSL/VEX and CUDA installation paths.
- `PROGRESS.md`: reviewers deciding whether M3.7's remaining shortfall is code, evidence or human
  promotion.
- `AUDIT_REPORT.md`: release reviewers evaluating the production-readiness claim.
- `evidence/current-main-acceptance-2026-08-15.md`: durable measurement record for exact-main WSL,
  release, attestation and installed-wheel acceptance.

## Non-impacts

No Python symbol, workflow, dependency, model manifest, gate, fixture, golden file or test floor is
changed. The current source fingerprint and WSL runtime receipt therefore remain valid. Existing
dated evidence is not rewritten; the new record supersedes only stale present-tense claims.

## Verification

- targeted claim/document tests covering README, PROGRESS, AUDIT and evidence;
- `git diff --check` and UTF-8 decoding;
- full `scripts/verify.sh` before any explicit-path commit; and
- exact-SHA PR CI before merge.
