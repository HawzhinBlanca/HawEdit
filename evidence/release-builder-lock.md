# Hash-locked release builder — 2026-08-09

## Finding

`hawedit-release` built twice with `--no-build-isolation`, but both builds inherited the same
ambient build backend. `pyproject.toml` allowed `setuptools>=68` and provenance recorded no builder.
That proved repeatability inside one environment, not reproducibility between builders.

The gap was measured against the same clean revision, `2c44e759f09941ebc65c87f9d6db6d7dcc93c9ed`:

| Allowed builder | Result |
|---|---|
| Setuptools 68.2.2 | Refused during metadata generation: `invalid command 'bdist_wheel'` |
| Setuptools 79.0.1 | wheel SHA-256 `716908c3e75258b0f7a940b908c09751a263b5b1762c0fb0d866594dfcad4d85` |
| Setuptools 84.0.0 | wheel SHA-256 `799c82b1582465bd63e80543c0628a28d05f5b9535a457fd9f0725444d78a509` |

The 79 and 84 wheels each had 56 members and the same 328,308-byte size. Only two members differed:
`WHEEL` named its Setuptools generator and `RECORD` carried the resulting checksum. That is enough
to change the distributed wheel identity while the old release command still declared each build
reproducible.

## Fix

`requirements/release-build.txt` pins the release frontend/backend to the official pure-Python
wheels for Pip 26.2.1 and Setuptools 84.0.0. The downloaded wheel digests were computed locally and
matched the SHA-256 values returned by the official PyPI JSON API; neither file was yanked:

- <https://pypi.org/pypi/pip/26.2.1/json>
- <https://pypi.org/pypi/setuptools/84.0.0/json>

`hawedit-release` now:

1. requires every `[build-system]` package to be exactly pinned;
2. requires that pin to agree with a one-hash-per-package release lock;
3. creates a private temporary virtual environment;
4. installs the lock with `--require-hashes --only-binary=:all: --no-deps --no-cache-dir`;
5. measures the resolved Pip, Setuptools and Python identity;
6. builds both wheel copies only with that private Python; and
7. stores the builder identity and lock digest in provenance schema 3.

The real release fixture creates this builder, builds twice, inspects the emitted `WHEEL` member
for `Generator: setuptools (84.0.0)`, and checks exact provenance. It does not mock the trust
boundary.

## Cross-Python proof on the real project

After the fix, clean revision `8d4810d28fd1c2edb3949492c2b5287a9fe06717` was released twice
through the production command with the same hash-locked frontend/backend:

| Builder Python | Wheel bytes | Wheel SHA-256 |
|---|---:|---|
| 3.11.15 | 329,973 | `7765db5414dd69f8679f0646b41376907978b95e68d9a260d7ad64e49cde34b9` |
| 3.12.10 | 329,973 | `7765db5414dd69f8679f0646b41376907978b95e68d9a260d7ad64e49cde34b9` |

The SPDX bytes were also identical. Provenance bytes intentionally differed because each document
records its measured Python version; that is transparent input identity, not unexplained artifact
drift.

## Mutation evidence

Three independent source mutations were run and restored:

1. `setuptools==84.0.0` → `setuptools>=68`: caught by the real project contract test.
2. Both wheel builds switched back from the private builder to the caller's Python: the real
   fixture emitted `Generator: setuptools (79.0.1)` and failed.
3. One nibble of the official Setuptools wheel hash changed: caught by the committed-hash test.

Result: **3/3 caught**. Focused settled result: **5 passed**, with Ruff, format and strict mypy
clean for `release.py` and its tests.

## Remaining boundary

This closes ambient build-tool drift and hash-locks the two Python packages that construct the
wheel. It does not sign the artifact, attest a publisher identity, or checksum Meta's
package-managed OmniASR downloads. M3.7 therefore remains PARTIAL.
