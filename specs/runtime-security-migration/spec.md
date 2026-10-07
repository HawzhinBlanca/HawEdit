# EARS Requirements

| ID | Requirement | Named automated regression |
|---|---|---|
| RM1 | WHEN WSL dependencies are installed, THE runtime SHALL bind urllib3 2.8.0 and Werkzeug 3.1.9 to independently verified upstream wheel hashes. | test_wsl_http_security_patches_bind_exact_upstream_wheels |
| RM2 | WHEN these utility pins change, THE runtime SHALL preserve every other existing requirement byte. | test_http_security_patch_preserves_other_runtime_requirements |
| RM3 | WHEN the patched runtime is provisioned, THE generation identity SHALL differ from the original generation without rewriting its receipt or environment. | test_http_security_patch_uses_a_distinct_environment_generation |
| RM4 | WHEN current source differs from qualified security evidence, THE security gate SHALL refuse admission rather than infer approval from installation. | test_checked_in_policy_binds_current_lock_and_assets_and_closes_report (existing, expected unresolved refusal) |

Real installation, hostile-input behavior, actual neural equivalence and rollback
need separate immutable evidence; lock-only regressions do not prove them.
RM4 maps the existing current-policy obligation; do not weaken it to make it pass.
