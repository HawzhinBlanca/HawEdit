# Impact Map

Actual current Serena map and baseline are in research.md. Before editing:

| Symbol | Affected Callers | Whole Regression Modules |
|---|---|---|
| wsl_vex_gate._run_bounded,14refs | _find_uv, _verify_uv, _run_hash_locked_audit, _execute_hash_locked_scanner; write/cleanup/output tests | test_wsl_vex_gate |
| native_io.run_native,8refs | exports; test_linux_control.execute; native control/capability tests | test_native_io, test_native_io_memory, test_native_control, test_native_capability_retention, test_linux_control |
| run_live_gate,18refs, unchanged signature/body | studio_host.capture_studio_deployment, main, live-gate tests | test_studio_host, test_studio_host_evidence, test_wsl_vex_workflow, test_wsl_vex_gate |

rg supplemented Serena for dynamic import_module/native_io test consumers.
New bounded_audit_io isolates audit-specific descriptors/limits/errors, not a
general producer abstraction. Existing ProcessOutput and caller signatures
stay unchanged. Native integer combined-limit callers/control frames keep
their existing defaults and refusal behavior. New explicit independent mode
uses no combined budget, requires both positive capped limits and rejects a
mixed/incomplete configuration before launch.

No changes to scanner lock/options/asset hashes/policy/receipt acceptance,
canonical transcript/models/routing, stage/publication or billing authority.
Capture refusals are not evidence of original Linux resource quiescence.

Before type/cleanup correction, actual two-pair Serena map of the new
_posix_capture (one capture_bounded caller) and capture_bounded (import/wrapper
in wsl_vex_gate), working source/ref/status unchanged:
C:/Users/Wareen/HawEditAuditCaptureCorrectionMap-20261009/serena-map.json,
SHA799211c836047a6f0a39d151876624a15084f4aaf0b7d792b8bd47ecea0e5a88.
Whole caller239checks initially passed. Strict Windows typing found absent
os.set_blocking declaration and reused optional stream variable. Dynamic
availability refusal is before launch; cleanup attempts every owned stream and
the original root even when one close fails, retaining uncertainty. No test
assertion was removed or weakened. Revalidate the whole callers after correction.
