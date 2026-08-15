# Impact map — WSL runtime-root override

## Planned source changes

| File | Symbols | Reason |
|---|---|---|
| `src/hawedit/wsl_setup.py` | shared root resolver, `main` | Centralize precedence and expose `--runtime-root`. |
| `src/hawedit/asr.py` | WSL setup imports, `WslOmniAsrProducer._runtime` | Consume the same validated configuration contract. |
| `scripts/setup-wsl-asr.ps1` | parameters and command arguments | Forward an operator-selected host root. |

## Planned tests

| File | Coverage |
|---|---|
| `tests/test_wsl_setup.py` | default/env/explicit precedence, empty/relative refusal, CLI forwarding |
| `tests/test_asr.py` | producer/setup root identity and refusal before receipt loading |
| `tests/test_harness_scripts.py` or nearest script contract test | PowerShell forwarding contract |

## Compatibility and non-goals

- Existing callers that pass `runtime_root` directly remain unchanged.
- Existing default locations remain unchanged when no override is configured.
- This unit does not provision model weights, modify receipts, relax directory checks, or claim a
  successful live ASR run.
- `BLUEPRINT.md` is unchanged; this closes an operator-path mismatch in the existing D-064 WSL
  bridge.
