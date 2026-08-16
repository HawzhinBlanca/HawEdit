# Research — WSL receipt newline portability

Parent program: `specs/true-10-10-acceptance/`.

## Reproduction

GitHub Actions run `31891464500`, attempt 3, checked out exact `main` SHA
`ac18067742eaa91ead7ec43eb25494730ad17d03` on the dedicated Windows/WSL runner. The
source-bound VEX step refused the otherwise-valid local receipt with:

> copied HawEdit checkpoint metadata does not match the host package

The receipt snapshot and normal Windows checkout contained CRLF bytes in
`models/revisions.json` (2,006 bytes). Actions checkout materialized the same Git object with LF
bytes (1,995 bytes). `package_digest()` intentionally canonicalizes universal newlines, so both
checkouts have source identity
`86fc8237d08e0037320e692e243d2ba74cf83ec93ba30612e3c32f97bb003fd3`. However,
`_validate_source_snapshot()` later compared the three safely-read metadata payloads byte for
byte, contradicting that portable identity contract.

## Symbol and caller map

Serena is not available in this environment, so `rg` was used as the documented fallback.

- `package_digest()` canonicalizes Python and checkpoint-metadata newlines.
- `_validate_source_snapshot()` is called by `_publish_source_snapshot()` and
  `load_wsl_runtime_receipt()`.
- `load_wsl_runtime_receipt()` is consumed by the WSL ASR producer, model readiness, and the live
  VEX gate.
- Existing tests prove source-digest newline stability but do not exercise metadata comparison
  between two checkout newline policies.

The trusted reads, exact metadata filename allowlist, single-link requirement for copied metadata,
and snapshot file allowlist are independent controls and must remain unchanged.
