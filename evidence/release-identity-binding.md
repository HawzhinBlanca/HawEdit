# Release artifact identity binding — 2026-08-09

## Reproduced gap

The old archive validator checked ZIP integrity, the presence of METADATA and required runtime
files. It did not compare distribution identity. Reconstructing a valid HawEdit wheel with:

```text
filename: hawedit-wrong-identity-9.9.9-py3-none-any.whl
METADATA Name: hawedit-impostor
METADATA Version: 9.9.9
```

produced `VALIDATOR_ACCEPTED` and `_wheel_metadata(...) == ("hawedit-impostor", "9.9.9", ...)`.
Byte-for-byte double builds, checksums and exact-SHA gate provenance would all remain internally
consistent, so the wrong identity could reach the attestation boundary.

## Enforced boundary

`hawedit-release` now reads `[project].name` and `[project].version` from the immutable Git export,
requires exactly one wheel METADATA record, parses the PEP 427 filename, and refuses unless all
three representations have one PEP-503-normalized name and exact version. Schema-5 provenance
records the accepted distribution/version, and the returned `ReleaseArtifact` exposes them.

The privileged GitHub job redoes the part it can measure without trusting checkout code: it opens
the transported wheel with Python's standard library, requires one METADATA record, requires the
normalized name `hawedit`, checks filename/METADATA name and version, then requires schema-5
provenance to contain those measured values. Only after that does the job attest and upload the
same explicit four-file set.

## Executable evidence

- `tests/test_release.py` independently mutates METADATA name/version and filename name/version,
  keeps a PEP-503 spelling control, and proves the real double-build path invokes the identity
  check on its immutable first source export.
- `tests/test_release_workflow.py` pins the no-checkout METADATA reader, `hawedit` name policy,
  filename equality and schema-5 distribution/version bindings.
- Focused release/workflow result before the canonical gate: **49 passed**, Ruff and mypy clean.
- Canonical gate after the change and upstream reconciliation: **1,825/1,825 passed**, zero skipped; Ruff, formatting, mypy over
  125 files and fresh JUnit evidence passed. Checksum-verified actionlint 1.7.12 reported zero
  findings for the edited release workflow.

This is artifact-identity evidence, not release-version policy. HawEdit still has no tag/version
promotion rule and no durable GitHub Release; those remain explicit M3.7 shortfalls.
