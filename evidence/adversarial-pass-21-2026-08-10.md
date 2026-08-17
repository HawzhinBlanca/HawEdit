# Adversarial pass 21 — normalized transcript publication

Date: 2026-08-10
Baseline: `4efcc86f2dd0c88b321c70de0c3d769cc712cd18`

## Finding

`TranscriptStore.write_norm` called `Path.write_text` directly on
`<media>.transcript.norm.json`. Unlike the canonical raw transcript, a norm is deliberately
rewritable, but that does not make a predictable in-place write safe.

The exact Windows hardlink reproduction before the fix reported:

```text
victim_changed= True
victim_prefix= {
  "media_id": "media-001",
nlink= 2
```

The call followed the final hardlink and overwrote an external victim. The same in-place path also
made a partial JSON document visible if encoding, disk I/O, or the process failed after truncation.
Finally, `write_norm` accepted an artifact derived from a different raw transcript; the mismatch
was caught only if somebody later called `read_norm`.

## Fix

Publication now runs under the per-media transcript lock and:

1. verifies the stored raw against its write-time digest;
2. refuses a norm whose `source_sha256` is not that exact raw;
3. writes UTF-8 JSON to a securely created private sibling and fsyncs it;
4. repeats raw integrity and identity checks immediately before publication;
5. atomically replaces the final path;
6. removes a failed stage without masking the primary exception.

Atomic replacement replaces a planted final link itself; it does not write through to the link's
victim. Re-normalization remains supported, and the read-side stale guard remains defense in depth
for artifacts produced by an old build or placed out of band.

## Discriminating controls

- a norm from a different raw is refused before a destination exists;
- a manually planted stale norm is still refused on read;
- rewriting a matching norm succeeds;
- a hardlink victim remains byte-identical and is no longer the published file;
- a simulated replace failure preserves the previous complete artifact and removes its stage;
- a simultaneous cleanup failure is attached to, and does not mask, the primary publication error.

Focused verification from checkout source:

```text
239 passed
Ruff: all checks passed
Ruff format: 2 files already formatted
mypy: success, no issues in 2 source files
```
