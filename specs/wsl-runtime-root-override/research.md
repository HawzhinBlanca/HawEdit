# Research — WSL runtime-root override

## Question

How can HawEdit provision and consume the same receipt-bound OmniASR runtime when the default
Windows LocalAppData drive cannot hold the runtime?

## Current behavior and reproduced gap

- `README.md` documents `HAWEDIT_WSL_RUNTIME` for advanced deployments.
- `WslOmniAsrProducer._runtime` reads that environment variable before loading a receipt.
- `provision_wsl_runtime` already accepts an explicit `runtime_root` and applies the existing
  plain-directory/reparse protections to it.
- The installed `hawedit-asr-setup` entry point and `scripts/setup-wsl-asr.ps1` expose only the WSL
  distribution. They call `provision_wsl_runtime` without a runtime root and therefore always use
  `default_wsl_runtime`.
- On this host the default C: volume is full, while the independent checkout and available capacity
  are on D:. Setting the documented environment variable makes the runner look on D:, but setup
  still writes or fails on C:. No valid current-source receipt can result at the path the runner
  later checks.

## Caller map

Serena is required by `AGENTS.md` but is not available in this Codex tool session. Exact `rg`
reference searches and direct source inspection were used instead.

| Symbol | Callers/consumers | Impact |
|---|---|---|
| `default_wsl_runtime` | setup, receipt loading, VEX gate, ASR producer | Remains the fallback only. |
| `provision_wsl_runtime(runtime_root=...)` | setup CLI and tests | Already owns safe creation and validation. |
| `load_wsl_runtime_receipt(runtime_root=...)` | ASR producer, probes, VEX | Must receive the same resolved root as setup. |
| `WslOmniAsrProducer._runtime` | canonical Stage 1 | Replace its ad-hoc environment parsing with the shared resolver. |
| `wsl_setup.main` | `hawedit-asr-setup` | Add explicit CLI support and environment fallback. |
| `scripts/setup-wsl-asr.ps1` | Windows operator path | Forward an optional exact root without inventing another default. |

## Chosen bounded design

1. Add one public resolver in `wsl_setup.py` for the host runtime root.
2. Precedence is explicit CLI/constructor value, then `HAWEDIT_WSL_RUNTIME`, then the existing
   platform default.
3. A configured value must be non-empty and absolute. Empty or relative values are configuration
   errors, never aliases for the current working directory.
4. Filesystem creation, reparse refusal, and receipt validation remain in the existing
   `_runtime_root_path` and receipt/provisioning boundaries.
5. Setup CLI, ASR producer, and PowerShell wrapper use the same contract.
6. No runtime bytes, model weights, credentials, dependency, or trust manifest is changed.
