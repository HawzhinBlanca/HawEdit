# ASR Stop Candidate Verification

2026-10-04; baseline 3fa765cd2dd48900fc900c949f63df2648eb7430 plus reviewed unit.
Package digest 1baa70289b3271f03e40646ead8b023194400feb2733c2f0c09eaa5e7f1715af.
Native HawaPC01 / Windows 26200 / CPython 3.12.10 / SQLite 3.49.1 /
pytest 9.1.1 / ruff 0.9.6 / mypy 1.15.0 / DBOS 2.29.0 / SQLAlchemy 2.0.52.
Private immutable run records, commands, runtime, before/after hashes and XML:
`C:/Users/Wareen/AppData/Local/HawEditEvidence/zar38-recovery-fdfe25-20261004/`.

## Test-First Evidence

- Initial complete new module: 18 failures, no errors/skips; XML SHA256
  3ea32a328792fa992a516bf12d4e52bb42c94c24caaab6426a4ea823c9abcc09.
- Initial implementation: 18 passes, no errors/skips; XML
  37f46a5f725531f12d2fe2e4d40d611774d7ac8ec7f7914790b0bdb4c743f305.
- Additional visual-order regression: 19 cases, 12 passes/7 failures, no errors/skips;
  XML 07dbc3ec44b646fd2fdff78b523e094c42b098d9f2ae291a0e58317f865eed33.
- Final complete caller modules (asr_stop, asr, adapter_identity, pipeline, transcripts,
  events, durable, studio_generation): 705 passes, no failures/errors/skips.
  Ended 18:01:04 UTC; JUnit 644.225 s / wrapper 647.028652 s; five source/test
  hashes unchanged. XML df24d5c7ab9e366d071493f1635bd3ce0cc9a3a8eb4d4e55bc208d413f134dde.
- Exact Git Bash `scripts/verify.sh --fast` subsequently exits 0; lint and strict types
  pass for 316 files. Separate ruff format check passes all 316. These are not full gate.

Tests use real decoded fixtures with injected failures to prove refusal contracts.
They are not real canonical inference, independent accuracy, speaker or delivery evidence.

## Real ZAR38 Replay

Source bd004519e4ed0254f5c4f5197aa501acc56ce957829f62ac0bdc4d7190ec1dd2;
raw e5e5f80f8afa2433b4a419b1d8e979101013bdf6acc3cc8a91e683d44346d7eb.
Actual champion producer identity remains source/audio/adapter bound.

Initial replay ended 18:00:00 UTC, exit 1: supplied raw was refused with all three gaps
and two rejected corrections, no visual windows, candidate or billed call. Existing
ingest configuration binding invalidated Stage 0, copied six historical files to
`stage0-recovery/recovery-a5c423cd4dfa4e9ca2e6bac6be703ad7`, and regenerated it.
The initial protocol's unchanged-file assertion failed; it also incorrectly classified
the upstream ingest_cache_reuse event as downstream. Cache replay was not reached.
Original failed record ac56ae76aea6621574f83dbc2f7d34898d4f67ba51b5e65f63c9234afa497700
is retained, not rewritten. Follow-up v2 precheck failed because recovery copies have new
file identities/timestamps; that protocol/script and captured failure remain retained.

Separate v3 protocol verifies six recovery copies' original hashes/sizes, records both
original and copied metadata, and freezes the current 15 paths plus seven recovery files.
Both genuine supplied and producer/source-bound cache calls pass refusal checks,
ending 18:02:44 UTC, exit 0. All 22 monitored files and package hashes unchanged in v3.
Measured calls 2.902280 s supplied / 3.541126 s cached on the runtime above; these are
cache/refusal timings, not fresh ASR, isolated performance or DBOS restart evidence.
Result SHA256 48f7685a7d4fe4daf37ad02e3deceecb0671cebb1afdfa06f0cee42c6552d238.
Neither replay invoked new canonical inference, cloud judging, rendering or publication.

## Remaining Gates

Exact full gate on the reviewed local commit is pending. Prior baseline gate had one
qualified VEX binding failure; do not rebind that review or infer this run's result.
No ledger completion, same-SHA CI, push, publication, independent native reference,
accepted model correction or 10/10 verdict. ZAR38's repeated-digit draft is unresolved.
First-failure exceptions retain diagnostic input in memory, not a durable prefix checkpoint.
