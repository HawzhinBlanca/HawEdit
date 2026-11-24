# Actual Caller Impact

Actual Serena map paths and baseline are recorded in research.md. Lines in the
raw LSP evidence are zero-based. References include embedded probe imports that
LSP cannot resolve; a bounded text inspection supplements, never replaces, LSP.

| Symbol | Actual caller / consumer | Verification |
|---|---|---|
| RUNTIME_REQUIREMENTS | RUNTIME_LOCK_SHA256, LOCKED_DISTRIBUTIONS, wsl_setup._LOCK_FILES, test_wsl_setup | Complete setup module, new patch hash regressions |
| RUNTIME_LOCK_SHA256 | wsl_setup._EXPECTED_LOCKS, test_vex, test_dependency_security, test_wsl_setup | Setup, dependency security, VEX modules; unchanged VEX refusal expected |
| LOCKED_DISTRIBUTIONS | wsl_setup._EXPECTED_PACKAGES, setup embedded identity probe, test_wsl_setup, test_dependency_security | Exact inventory, official real candidate install/readiness |
| _environment_digest | _generation_name, _build_receipt, _generation_is_complete, load_wsl_runtime_receipt, provision_wsl_runtime | Different generation identity; no function edit planned |
| provision_wsl_runtime | wsl_setup.main and setup tests | Existing explicit-root API, real isolated install; no function edit planned |
| load_wsl_runtime_receipt | WslOmniAsrProducer._runtime, probe_wsl_runtime, run_live_gate, setup tests | Existing receipt drift guards and actual live audit |
| probe_wsl_runtime | models._probe_canonical_omni_runtime, run_live_gate, setup tests | Actual canonical asset/import checks, not forward-pass claims |
| HOST_LOCK_SHA256 | environment._load_host_lock_sha256, environment contract validation, release/environment tests | T2 pending targeted generator research; not modified by T1 |

T1 only edits the two runtime requirement entries and truthful lock documentation.
All model package pins, build locks, canonical assets, startup/receipt/ASR APIs,
host locks, qualified VEX policy, reviewer trust and HTTP readiness remain intact.

## T2 Narrow Checkpoint Metadata Mitigation

Actual model-security-consumers-map-20261007, clean140d06d before edit:
assert_transformers_config_safe -> QwenSoraniValidator._load (asr.py),
load_processor_and_model (qwen_visual.py), official validator contract test in
test_asr.py and all existing model-config guard cases in test_models.py.
The returned type and existing failures stay unchanged. New shard helper has
no prior callers; only this already-mapped guard invokes it, inside the existing
verified read lock. No producer, integrity verifier, signature or runtime API edit.
Complete test_models/test_asr/test_qwen_visual caller modules plus new named shard
regressions, actual tiny-model attack refusal and real index compatibility required.
No claim of whole-model visual quality, library-wide fix or approved VEX.
