# Impact map — editable model-profile audit

## Directly changed

- `src/hawedit/environment.py`
  - `audit_installed_profile`
  - a small current-target lock-name/root helper if needed to avoid duplicating selection logic
- `tests/test_environment.py`
  - editable positive path
  - lock/manifest/root negative paths
- `tests/test_model_fetch.py` only if needed for the production caller seam

## Callers and preserved behavior

- `src/hawedit/model_fetch.py::_download_client`
  - gains a working documented editable-install preflight
  - still refuses before import/network on any audit failure
- `resolve_installed_host_lock`
  - remains the public wheel data resolver; no relaxation of RECORD authentication
- `audit_environment`
  - unchanged; canonical exact-inventory gate behavior remains separate and strict
- release wheel smoke and installed-wheel provisioning tests
  - must remain green and must continue exercising RECORD-bound lock resolution

## Non-impacted surfaces

No model bytes, download transaction, WSL runtime, GPU adapter, pipeline, release workflow,
credential, or rendering code is changed by this unit.
