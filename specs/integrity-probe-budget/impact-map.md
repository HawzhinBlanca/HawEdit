# Impact Map

Actual Serena baseline/map/hash are recorded in research.md. Only two existing
production functions change; no existing test/fixture assertions are removed.

| Symbol | Actual Callers / Surface | Required Regressions |
|---|---|---|
| wsl_setup.probe_wsl_runtime | models._probe_canonical_omni_runtime, studio_host.capture_studio_deployment, wsl_vex_gate.run_live_gate; direct test_live_asset_probe_cannot_mutate_the_receipt_bound_source and imports/exports | Whole test_wsl_setup, test_models, test_studio_host; new default/selected/invalid budget, failure/drift/malformed contracts |
| wsl_vex_gate.run_live_gate | studio_host.capture_studio_deployment, wsl_vex_gate.main; existing pinned audit, environment parity, refusal, policy ABA, scanner cleanup, receipt drift, nonoverwrite tests | Whole test_wsl_vex_gate/test_studio_host; new selected-budget forwarding and pre-receipt invalid-budget contracts |
| load_wsl_runtime_receipt | Producer._runtime, probe, live gate and receipt/source/dependency drift tests | Unchanged, retain actual checks and whole callers' coverage |
| _run_bounded | Scanner tool/storage/version/install/audit, failure delegates, actual excess-output test | Unchanged; its reader joins and original Linux ownership remain separate T3 work |
| LinuxOwnerChannel | Only export/type annotation; no current production adoption | Unchanged; no worker/GPU/provider cleanup acceptance inferred |

Default probe deadline changes120to300seconds to match current live scanner
budget. Existing explicit live CLI --timeout-seconds now reaches final probe.
No new CLI flag/dependency, accepted policy data or model bytes. Neither models
nor studio host signatures change. Existing direct calls get bounded300default,
not a ready flag. Failure remains refusal with original cause and no claimed
Linux cleanup. Dynamic dispatch/global test monkeypatches remain covered by the
whole applicable modules and exact full gate, not static reference count alone.
