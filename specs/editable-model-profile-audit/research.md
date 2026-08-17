# Research — editable model-profile audit

## Problem

The documented source-checkout provisioning path creates a dedicated environment with
`scripts/install-host.sh ... models`, which installs HawEdit as a PEP 660 editable project.
`hawedit.model_fetch._download_client()` then calls
`hawedit.environment.audit_installed_profile("models")` before importing Hugging Face.

On a real clean Windows CPython 3.12 model-fetch environment, that audit selects the editable
HawEdit distribution correctly but then calls `resolve_installed_host_lock()`. That resolver
authenticates wheel data through `RECORD`; an editable distribution does not install the
`share/hawedit/requirements/host-models-*.txt` data-file entry, so the documented command is
refused before network access:

`installed HawEdit RECORD must name exactly one ... host-models-windows-py312.txt; found 0`

The wheel workflow is valid and must remain RECORD-authenticated. A locally built wheel was
used only as a diagnostic control; after replacing the editable install with that wheel, the
same environment audit passed and two public Qwen checkpoints were provisioned and verified.

## Current symbols and callers

Serena is not available in this workspace, so the required symbol/reference map was produced
with `rg` against the current protected-main tree.

- `audit_installed_profile()` — runtime subset audit used by model provisioning.
- `_runtime_hawedit_distribution()` — selects the one authoritative editable record, or the
  one wheel record.
- `_has_editable_direct_url()` / `_editable_root()` — already provide strict PEP 660 identity
  and checkout-root validation.
- `resolve_installed_host_lock()` / `resolve_installed_hawedit_data()` — wheel-only,
  RECORD-authenticated data resolution.
- `_read_project_manifest()` — source-checkout dependency declaration.
- `_read_installed_manifest()` — installed-wheel dependency declaration.
- `validate_host_lock()` — authenticates lock bytes against the code-bound hash map and checks
  the project dependency contract when a project root is supplied.
- Sole production caller: `model_fetch._download_client()`.

## Design conclusion

`audit_installed_profile()` must branch on the already-authoritative distribution type:

- Editable distribution: resolve its strict `direct_url.json` root; resolve the current target
  lock beneath that root's `requirements/`; call `validate_host_lock(..., project_root=root)`;
  and read dependencies from that root's `pyproject.toml`.
- Wheel distribution: preserve the existing RECORD-authenticated data-file resolver and wheel
  metadata manifest path unchanged.

Both branches must retain the same code-bound lock SHA, project version, direct-dependency
coverage, and complete locked-distribution inventory checks. No fallback from a malformed
editable install to wheel semantics is allowed.

## Blueprint and prior decisions

This is provisioning/runtime integrity work supporting BLUEPRINT §7 rather than a behavior
divergence. It preserves the locked-host-environment and immutable-metadata decisions already
implemented in the environment/model-fetch surfaces; no new dependency or architecture is
introduced, so no new ADR is required.
