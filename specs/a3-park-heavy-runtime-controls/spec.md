# Spec — Park heavy runtime controls (a3-park-heavy-runtime-controls)

EARS acceptance criteria (`tests/test_a3_park_heavy_runtime_controls.py`). `security/wsl-asr-vex.json` and `tests/test_vex.py` remain untouched per `#16` for lead merge-time VEX re-pinning.

- **AC1** WHEN `create_omni_asr_producer` (or `hawedit.pipeline`) runs without `--strict-runtime` or `HAWEDIT_STRICT_RUNTIME=1`, THE system SHALL park source-digest `.ready` receipt verification and resolve plain WSL Python on desktop runs without failing on a missing receipt.
  `test_desktop_default_bypasses_heavy_runtime_controls`

- **AC2** WHEN `--strict-runtime` or `HAWEDIT_STRICT_RUNTIME=1` is active (or `WslOmniAsrProducer` is invoked in strict mode), THE system SHALL enforce `load_wsl_runtime_receipt` verification and `gpu_runtime` visibility restrictions without weakening existing strict checks.
  `test_strict_runtime_flag_enforces_full_receipt_and_admission`, `test_gpu_runtime_strict_audit_still_rejects_visibility_overrides`

- **AC3** WHEN `hawedit.web` checks `protected_studio_enabled()` without `--protected-studio` / `HAWEDIT_PROTECTED_STUDIO=1`, THE system SHALL report desktop mode enabled (`False`); WHEN `HAWEDIT_PROTECTED_STUDIO=1` or `--protected-studio` is active, protected 503 admission behavior SHALL remain enforced.
  `test_studio_protected_mode_is_opt_in`
