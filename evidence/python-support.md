# Python support and installed-wheel promotion — 2026-08-09

## Reproduced false claim

The project declared every Python `>=3.11` supported and `scripts/setup.sh` selected any such
interpreter. A real `uv pip compile` for CPython 3.13 could not resolve the base graph:
`klpt==0.1.7` requires `chunspell==2.0.4`, whose published artifacts stop at CPython 3.12 and
provide no source distribution. The isolated ASR stack also caps `omnilingual-asr==0.2.0` at
Python 3.12. Equivalent 3.11 and 3.12 resolver probes succeeded. Admitting 3.13 was therefore a
false installation promise, not untested optimism.

## Enforced range and promotion

- `requires-python` is exactly `>=3.11,<3.13`.
- Setup selects only a base 3.11/3.12 interpreter and independently refuses a stale `.venv` made
  by any other version.
- The protected `gate` job depends on a separate full Python 3.12 install/ffmpeg/zero-skip gate, so
  the required status cannot succeed while the supported ceiling is red. The canonical job remains
  a single job named `gate`, preserving the exact release verifier's contract.
- Release promotion inserts a no-checkout, unprivileged 3.11/3.12 matrix between build and
  attestation. Each runner downloads the exact build transport, creates a fresh venv, installs the
  one wheel using binary dependencies, runs `pip check`, imports installed package-data paths from
  outside the checkout, and starts all six console entry points with `--help`. The privileged
  attestation job needs every matrix leg, so ZIP shape alone cannot promote an unusable wheel.

## Measured locally

The edited tree produced `hawedit-0.1.0-py3-none-any.whl`, 367,859 bytes, SHA-256
`222776e1d10e0292930859caefed69def0a1225a387fb5299a90c00776b8381c`. Fresh Windows Python
3.11.15 and 3.12.13 venvs each installed that exact wheel with binary-only dependencies; `pip
check`, all five installed font/model metadata paths, and all six CLI help probes passed.

The hosted Python 3.12 prerequisite and release smoke matrix remain live acceptance items until
this workflow revision reaches protected `main`. This narrows and enforces interpreter support; it
does not create the still-open hash locks for transitive deployment dependencies.
