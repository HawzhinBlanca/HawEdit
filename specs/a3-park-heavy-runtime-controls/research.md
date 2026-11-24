# Research — Park heavy runtime controls (a3-park-heavy-runtime-controls)

Date: 2026-11-18. Host: `HawaPC01`, commit `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf`. Serena MCP was unavailable; modules and callers were mapped via `rg` and direct inspection.

## 1. Problem Statement

As documented in `specs/pro-grade-program/gemini-task-sheet-2026-11-18.md §1` and observed in `evidence/a2-pipeline-refusal-2026-11-18.md`, heavy enterprise/multi-tenant runtime controls currently stand directly on the default path of CLI runs, Studio UI generation, and normal code edits:

1. **WSL receipt & snapshot digest gate (`asr.py:1842-1874`, `wsl_setup.py:1172-1298`):**
   - `WslOmniAsrProducer._runtime()` rejects running OmniASR unless `%LOCALAPPDATA%\HawEdit\wsl-asr\sources\<package_digest(src/hawedit)[:16]>\.ready` exists alongside an immutable `__pycache__`-free source snapshot and exact WSL package lock hashes. Every code edit invalidates the digest and stops real-media execution.
2. **VEX source-digest CI freeze (`security/wsl-asr-vex.json`, `tests/test_vex.py:27-30, 140-163`):**
   - `tests/test_vex.py` binds `REVIEWED_VEX_SOURCE` and `security/wsl-asr-vex.json` to exact `package_digest(src/hawedit)` (`a7b54139328bd7a9...`). As already encountered by `specs/kurdish-rtl-base-direction/plan.md:90-102`, **any change anywhere in `src/hawedit/` breaks `verify.sh`**, forcing manual owner re-pins on every feature PR (`D-333` addenda, `D-334` addendum). Moreover `security/wsl-asr-vex.json` `"expires": "2026-11-14"` is already expired.
3. **Host CUDA lock & visibility ban (`gpu_runtime.py:20-28`):**
   - `gpu_runtime.audit_gpu_runtime()` hardcodes `_TORCH_VERSION = "2.13.0+cu130"`, `_CUDA_VERSION = "13.0"`, `_CUDNN_VERSION = 92000`, and explicitly forbids `CUDA_VISIBLE_DEVICES` and `NVIDIA_VISIBLE_DEVICES`.
4. **Heavy Studio & Linux root/namespace isolation modules (~20 modules):**
   - `studio_host.py`, `studio_authorization.py`, `studio_admission.py`, `studio_billing.py`, `studio_execution.py`, `studio_queue.py`, `studio_runtime.py`, `studio_submissions.py`, plus `linux_bootstrap.py`, `linux_control.py`, `linux_rooted_launch.py`, `linux_rooted_worker.py`, `linux_scope.py`, `linux_snapshot.py`, `linux_thread_name.py`, `linux_thread_registry.py`, `linux_worker_resources.py`, `environment.py`, `host_lock_hashes.py`, `wsl_vex_gate.py`, `vex.py`.
   - None of these deliver clips today (`web.py:591,814` returns `503 studio_runner_unavailable` waiting for the "protected studio producer worker"), yet keeping their digest/admission contracts unparked blocks single-user desktop runs and CI.

## 2. Design Principle (Task Sheet A3)

- **Park, do not delete:** Keep every heavy security/isolation module and its dedicated unit tests working in the codebase behind explicit strict flags (`--strict-runtime` / `HAWEDIT_STRICT_RUNTIME=1` for CLI/Studio; opt-in `HAWEDIT_STRICT_VEX_PIN=1` or release-profile gate for source-digest VEX pinning), rather than deleting hardening code or silently relaxing assertions inside strict mode.
- **Requires explicit `[HAWA]` owner approval:** Moving default runtime behavior and `test_vex.py`'s source-digest lock behavior is a security/policy change governed by `DECISIONS.md` (`D-333`, `BLOCKED.md #24`) and needs ADR **D-337**.

Answers to: `BLUEPRINT.md` §6, §7; `DECISIONS.md` D-333, D-334; `BLOCKED.md` #24.
