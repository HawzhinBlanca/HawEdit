# Deterministic release SBOM evidence · 2026-08-09

## Claim

Every successful `hawedit-release` publication includes deterministic SPDX 2.3 JSON tied to the
exact wheel and Git revision. It discloses the bundled Noto font and every dependency declared
by wheel METADATA without presenting unresolved requirements as installed versions.

## Project regression

`tests/test_release.py` builds a real fixture wheel twice in independent directories. It checks:

- one root package with the exact wheel SHA-256 and version;
- one contained Noto Naskh Arabic component with the font-byte SHA-256 and OFL-1.1;
- `DEPENDS_ON` for a base requirement and `OPTIONAL_DEPENDENCY_OF` for an extra;
- byte-identical SBOM generation for the same wheel/revision/epoch;
- an exact four-file public set: wheel, SPDX JSON, provenance, `SHA256SUMS`;
- checksum coverage for wheel, SBOM and provenance; and
- write-once release publication under a competing existing directory.

Focused result: `3 passed`; Ruff and mypy pass for `release.py` and its tests.

Full rebased project gate: `1,145 collected, 1,145 passed, 0 skipped`; Ruff, format and mypy clean.

## Independent standards validation

The generator was run against the previously released HawEdit wheel, then checked by a fresh
Python 3.12 environment containing only `spdx-tools==0.8.5` and its dependencies:

```text
pyspdxtools --infile .gate/spdx-audit-b9b23e6.spdx.json --version SPDX-2.3
exit 0
```

That tool is independent of HawEdit's parser and tests. The format and relationships follow the
official SPDX 2.3 package/checksum and relationship definitions.

## Boundary

This is an artifact SBOM. It intentionally does not claim an installed transitive dependency
graph, a vulnerability scan, signed authenticity, or checksums for package-managed OmniASR
downloads. Those are distinct promotion requirements, and the release ledger remains PARTIAL.
