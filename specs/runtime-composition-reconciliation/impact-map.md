# Impact map — runtime composition reconciliation

## Direct changes

- `src/hawedit/wsl_setup.py`: rename/export `_prefix` as `wsl_prefix`; update internal callers.
- `src/hawedit/asr.py`: import the public symbol without a private alias.
- `src/hawedit/wsl_vex_gate.py`: remove `_wsl_prefix`; use `wsl_prefix` at every command seam.
- `tests/test_wsl_setup.py`: import/assert the public builder.
- `tests/test_wsl_vex_gate.py`: prove VEX command construction consumes the shared symbol.
- `security/wsl-asr-vex.json` and `evidence/wsl-asr-vex.md`: reviewed source-digest rebind only.

## Verified unchanged consumers

- ASR producer and worker transcript assembly.
- Visual frame extraction and temporal patch parity.
- Pipeline device preflight/composer construction.
- Qwen, VideoChat3, and TimeLens lifecycle cleanup.

No dependency, checkpoint, WSL package, advisory disposition, cloud route, render, or delivery
contract changes in this unit.
