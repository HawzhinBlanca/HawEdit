# Two builds of one commit

This evidence is about a local wheel candidate. It is not release authorization: production
publication additionally requires exact-SHA CI, provenance, SBOM, and GitHub attestation.

## Two independent causes were measured

The original build had no `SOURCE_DATE_EPOCH`. Two ambient `pip wheel` invocations over one tree
produced equal-size archives with different ZIP timestamps and hashes:

```text
333,362 bytes  sha256 a7c3b2f1c280aff4...
333,362 bytes  sha256 38d1d2475c46e120...
```

Setting the epoch fixed that machine's timestamp drift, but did not make the builder an identity.
On 2026-08-09, commit `e314c3232f414f3e90ed82ed67a5a1ff0f8b0488` was built with the old
script through two available Python environments. Both used the same clean Git tree and commit
epoch and produced the same 473,534-byte filename, but their backend versions differed:

```text
builder A: pip 26.2.1, setuptools 84.0.0
sha256 d7d3486c082ea372faff597b52a9e430ff99b399f3a59cd280236aac7ec3ff9e

builder B: pip 26.2.1, setuptools 79.0.1
sha256 0246fc0c414cb6bd3cf00f840a8649ed5a90eb9af88c62615ae9ba7a1aacdad9

equal: false
```

`SOURCE_DATE_EPOCH` alone therefore did not support the former "any machine" claim. The script
also only warned about a dirty worktree, allowing uncommitted bytes to be stamped as a commit.

## Current contract

`scripts/build-wheel.sh` delegates to the same candidate builder used by `hawedit-release`:

1. require one clean Git HEAD; dirty and untracked input is refused;
2. export that exact Git object twice into separate immutable source directories;
3. create a private builder and install `requirements/release-build.txt` using
   `--require-hashes --only-binary=:all: --no-deps`;
4. measure the builder Python, `pip`, `setuptools`, and lock SHA-256;
5. build each pristine source independently with the commit epoch;
6. require equal wheel names and SHA-256s and validate source/filename/METADATA identity;
7. recheck the live checkout identity, then atomically publish a previously absent directory.

The JSON result records the exact builder identity and artifact digest. Re-running against the same
output refuses instead of replacing bytes already handed to another process.

The honest reproducibility statement is now narrow: two independent builds of one clean Git object,
under the same measured Python and hash-locked frontend/backend contract, must be byte-identical.
Different Python builds, operating systems, architectures, or future backend locks are distinct
builder identities and are not asserted equal by this test.

## Executable proof

`tests/test_release.py` proves local and production paths share the independent Git snapshots and
locked builder, refuse dirty input before creating output, and publish write-once. `tests/test_build.py`
runs the shell helper twice, compares the actual wheel bytes, checks every ZIP timestamp against the
commit epoch, and verifies both reports name `pip==26.2.1`, `setuptools==84.0.0`, and one lock digest.
