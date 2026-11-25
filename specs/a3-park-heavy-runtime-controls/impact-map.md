# Impact map — Park heavy runtime controls (a3-park-heavy-runtime-controls)

Serena MCP was unavailable; callers mapped via `rg` across `src/` and `tests/`.

| Control / Module | Callers in `src/` | Tests & Enforcement Surfaces |
|---|---|---|
| `load_wsl_runtime_receipt` (`wsl_setup.py:1172`) | `asr.py:1862`, `wsl_setup.py:1383`, `wsl_vex_gate.py:581` | `tests/test_asr.py:130`, `tests/test_wsl_setup.py`, `tests/test_wsl_vex_gate.py`, `tests/test_integrity_probe_budget.py` |
| `REVIEWED_VEX_SOURCE`, `security/wsl-asr-vex.json` | `src/hawedit/vex.py`, `src/hawedit/wsl_vex_gate.py` | `tests/test_vex.py:27-30, 140-163`, `tests/test_studio_host_evidence.py` |
| `gpu_runtime.audit_gpu_runtime` (`gpu_runtime.py:16`) | Standalone CLI (`__main__`) only — not currently wired into `pipeline.py` | `tests/test_gpu_runtime.py` |
| `linux_*` (9 modules) | Self-contained (`linux_bootstrap` -> `linux_scope`, `linux_rooted_launch` -> `linux_rooted_worker` -> `linux_snapshot` -> `linux_thread_*` -> `linux_worker_resources`); not wired into `pipeline.py` | `tests/test_linux_*.py`, `tests/test_rooted_controller.py`, `tests/test_worker_resources.py` |
| `studio_host`, `studio_authorization`, `studio_admission`, `studio_billing`, `studio_execution`, `studio_queue`, `studio_runtime` | Interconnected only within `studio_*`; `web.py:591,814` currently returns 503 waiting on them instead of invoking them | `tests/test_studio_host*.py`, `tests/test_studio_authorization.py`, `tests/test_studio_billing.py`, `tests/test_studio_execution_input.py`, `tests/test_studio_queue.py`, `tests/test_studio_runtime.py`, `tests/test_trusted_producer_parity.py` |
| `environment.validate_host_lock` / `audit_installed_profile` | `ffmpeg_setup.py:17`, `models.py:47`, `model_fetch.py:35`, `studio_artifacts.py:21`, `studio_host.py:24`, `vex.py:21` | `tests/test_environment.py`, `tests/test_host_dependencies.py`, `tests/test_studio_profile.py` |
| Shared docs (only upon approval) | `DECISIONS.md` (new `## D-337`), `BLOCKED.md` (cross-reference `#24`), `PROGRESS.md` | Checked by `tests/test_claims.py` |
