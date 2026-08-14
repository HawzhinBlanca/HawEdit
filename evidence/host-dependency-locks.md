# Host dependency lock evidence — 2026-08-09

## Claim

The base wheel runtime, canonical `dev,media` gate graph, and minimal `models` provisioning
graph no longer ask a live resolver to choose transitive versions. Twelve committed locks cover
CPython 3.11/3.12 on x86-64 Linux and Windows. Each package line contains one exact
version and one SHA-256 for the target-compatible wheel selected by `uv==0.11.26`; sdists
are excluded.

The resolver cutoff is `2026-08-09T00:00:00Z`. The generator consumes official PyPI wheel
records plus PyTorch's official CPU index, rejects every other host, and reduces uv's PEP 751
target result to one wheel hash rather than accepting `--generate-hashes`' broad cross-platform
hash set. Run `python scripts/lock_host_dependencies.py --check` to independently re-resolve and
compare all twelve targets.

The generator also writes `hawedit.host_lock_hashes`: a code-bound SHA-256 identity for the
exact bytes of every lock. Validation checks this trusted mapping before parsing any header or
requirement, so changing a transitive line and its wheel hash is not authorized by the lock's
self-declared contract. The four base and four models locks plus this mapping ship in the wheel.

## Installation and identity boundary

`scripts/install-host.sh` validates the selected lock's OS, Python minor, scope, extras and
semantic dependency-contract digest before its first network request. Direct-script mode loads
the generated sibling hash table explicitly, so this preflight works before HawEdit exists and
cannot borrow trusted bytes from another installed checkout. It then uses pip
`--require-hashes --only-binary=:all:`. HawEdit itself is installed with `--no-deps
--no-build-isolation`, so neither runtime dependencies nor the build backend are resolved a
second time. `pip check` and `hawedit.environment` finally require the complete installed
distribution inventory—missing, unexpected, duplicate and version-drifted packages all fail.

`scripts/setup.sh`, both canonical gate jobs, and both release-smoke Python versions consume
these locks. Release smoke installs the wheel with `--no-index --no-deps` and audits the clean
installed environment against the exact-SHA base lock.

The four `models` locks contain base plus `huggingface-hub==0.36.2` and its transitives; they do
not pull Torch, media, pytest or mypy into a provisioning environment. The release wheel carries
those locks under `share/hawedit/requirements`. `hawedit.environment --show-lock models` resolves
the installed current-target file. An operator installs it explicitly in a dedicated venv with
hash mode; the fetch command never installs packages itself. Before importing the client,
`audit_installed_profile("models")` requires every locked transitive at its exact version while
allowing unrelated packages, so later drift also refuses provisioning.

Packaged data is located from the one authoritative HawEdit distribution's raw wheel `RECORD`,
not an assumed `sys.prefix` layout. Normal installs use `Distribution.locate_file`; a real
`pip --target` install needs a distribution-root relocation because CPython's
`Distribution.files` silently filters pip's still-`../../share/...` data entries after moving
them under the target root. Both paths require exactly one candidate whose byte size and SHA-256
match `RECORD`. Duplicate HawEdit records, duplicate data entries, traversal-shaped paths,
absent files, hash drift, and local-wheel `direct_url.json` records are handled fail closed. Only
`dir_info.editable == true` is treated as an editable source installation.

## Measurements

- Static matrix/contract, adversarial environment, and workflow tests: 42 passed. They include
  lock-byte tampering, same-version duplicate HawEdit metadata, local-wheel direct URLs,
  target-style data locations, dependency drift and setuptools' reordered wheel metadata.
- Fresh pinned-resolver re-resolution: all 12 generated target graphs and generated lock-byte
  identities matched exactly.
- Fresh Windows CPython 3.12 base lock: hash install, editable no-deps build, `pip check`, and
  exact inventory audit passed.
- Fresh Windows CPython 3.12 gate lock: 37 hashed packages, including
  `torch==2.13.0+cpu`, installed from a short clean venv; `pip check` and exact inventory audit
  passed.
- Fresh actual Windows CPython 3.12 wheel install outside the checkout: wheel installed with
  `--no-index --no-deps`; its own `RECORD` resolved the packaged base lock; five hashed packages,
  `pip check`, and exact inventory audit passed. Wheel metadata's canonical
  `Requires-Python: <3.13,>=3.11` order was accepted semantically without weakening the exact
  two-bound parser.
- A second fresh actual wheel venv resolved its packaged models lock, installed 19 hashed
  packages, passed `pip check`, passed the exact models inventory audit, and passed the runtime
  subset audit (`hawedit-installed-profile-ok:19`).
- Fresh standard Windows CPython 3.11 venvs repeated the packaged-wheel base and models routes;
  both hash installs, `pip check`, exact audits, and the 19-package models runtime audit passed.
- The source-tree installer independently bootstrapped the models profile from an empty Windows
  CPython 3.12 venv, installed the same 19 hashes, built HawEdit editable without isolation or
  dependency resolution, and passed its final exact inventory audit.
- A real `pip --target` wheel install resolved and authenticated both the packaged base lock and
  model integrity manifest from the target's relocated `share/hawedit` tree.
- A deliberately deep disposable venv failed while unpacking Torch at a 252-character license
  path (`WinError 206`). HawEdit's normal `.venv` spelling puts the same path at 221 characters;
  the failure is recorded rather than misreported as lock success.

## Honest boundary

These are CPU host locks only. CUDA/GPU and WSL OmniASR graphs have different indexes,
platform constraints and operational receipts and are locked in their own lanes. The optional
`models` downloader extra is isolated from base and gate rather than smuggled into those graphs;
changing base, dev, media or models dependencies invalidates the relevant lock contract and fails
closed until regeneration.
