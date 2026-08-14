# WSL runtime transaction and receipt — 2026-08-09

## Reproduced failures

- Two setup calls entered the same mutable `runtime/venv` concurrently.
- A plain `.ready` marker was accepted even when `venv/bin/python` did not exist.
- Multiple source fingerprints could remain positive over one venv after a later failed setup
  partially changed that environment.
- `ModelStore` treated the OmniASR Python package as both checkpoints being available even when
  the canonical asset cache was absent.
- A copied worker tree could retain an unmanifested native module or unchecked-hash bytecode that
  was invisible to the old top-level-`*.py` fingerprint.
- A Python-only snapshot omitted the trusted checkpoint manifests. Qwen-ASR in WSL then had no
  `integrity.json` and could not verify the hard-segment validator checkpoint.
- Setup invalidated a valid receipt before long provisioning, so a failed concurrent attempt made
  a still-valid source snapshot/generation unavailable.

## Enforced transaction

`src/hawedit/wsl_setup.py` now serializes every source, venv and receipt mutation with one
cross-process runtime lock. Setup stages an exact Python-only worker tree in a unique directory,
validates every member, and atomically publishes the snapshot. Published snapshots refuse links,
bytecode caches, native modules, unexpected files and unexpected directories.

The schema-2 readiness receipt binds:

- the complete 64-hex worker-source SHA-256, exact snapshot directory, and exact receipt-owned
  `sources.json`, `revisions.json` and `integrity.json` metadata copy;
- one versioned/revalidated venv generation and its dependency-specification digest;
- the actual distro, UID, home, interpreter path and Python 3.12 version;
- exact top-level package versions;
- canonical OmniASR asset cache, byte total and identities; and
- the observed CUDA device count required by the two-model route.

Loading re-hashes the copied source and executes the recorded interpreter to compare its live
identity and package versions with both the generation receipt and readiness receipt. Asset
readiness is re-probed rather than inferred from importability. A legacy flag, missing interpreter,
changed package, changed source member, forged receipt or mismatched generation fails closed.

Setup stages new snapshots/generations without invalidating a previously valid receipt; failure
leaves that receipt readable. Its result crosses WSL through a random host-created file opened
without following links, checked as one regular link, bound by descriptor/path identity, flushed
and revalidated before host publication. A substituted hardlink or symlink is neither truncated
nor unlinked as though HawEdit owned it.

This is not a claim that the venv bytes are immutable. Transitive packages are not yet represented
by a complete hash manifest; that remains the release supply-chain shortfall in M3.7.

## Executable controls

`tests/test_wsl_setup.py`, `tests/test_asr.py` and `tests/test_models.py` cover concurrent setup,
failed mutation, missing interpreters, receipt drift, source additions, symlink/reparse/hardlink
lock attacks, long Windows lock contention and actual execution of the embedded identity probe.
`tests/test_omni_assets.py` applies the same safe long-lock discipline to model provisioning.

Focused current verification: 31 WSL tests and 109 combined WSL/model tests passed with zero
skips. The clean Git-clone Python 3.12.13 gate passed 1,525/1,525 with zero skips; Ruff, formatting,
mypy and fresh JUnit evidence were clean.
