---
commit: 7f2f5ada27c1e3616047798ec35c0076c39f6439
media_sha256: n/a (canonical regression suite, not ZAR inference)
host: HawaPC01 Threadripper3990X Windows26300 CPython3.12.10; WSL6.18.54.1-microsoft-standard-WSL2
command: bash scripts/verify.sh
status: WIP; exit1, billing sidecar and independent VEX failures, no gate/CI pass
libraries: pytest9.1.1 ruff0.9.6 mypy1.15.0
---

# Controller Profile Full Gate

Exact committed-source command terminates exit1:6405passed,2failed,0errors,
0skips,2607.79s pytest/2607.200s JUnit. Lint, strict typecheck408files and
format408files pass. No gate grading success, ledger promotion, current CI,
model/ASR release or delivered-media claim.

Raw log C:/Users/Wareen/HawEditGate-7f2f5ad-20261014.log,
SHAdc7210c43c66dc58701f20b07717c0b0d8e9b4160205fbb240371f51908c5e3b.
Unchanged XML copy C:/Users/Wareen/HawEditGate-7f2f5ad-20261014.xml,
SHA04bd3381d8d7f43755ef69ae37cc2875bff360907571de23a916aef34a80a691.
Source package31b57b84c0a8a2de28c7f7e38296333bd2c97f9b43c0a75f6191f3e313bfadfa.

Failures:
- test_studio_billing_concurrent_jobs_cannot_oversubscribe_pool: actual storage
  validation raises StudioStorageError on billing.sqlite3-shm after count's
  connection closes; generation refuses. This is a reliability counterexample,
  not an observed charge or oversubscription. Preserve the entire traceback;
  do not discard it as a flaky pass on rerun. Existing disappearance handling
  omits that validation error family; approved T3 follow-up retains stable unsafe
  file/refund/provider/budget controls and adds real transition coverage.
- test_checked_in_policy_binds_current_lock_and_assets_and_closes_report:
  independent VEX binds81f6f606..., not current31b57b84... source. Expiry/source
  review remains BLOCKED #24. No self-renewal or rebinding was performed.

The new controller profile regressions pass inside this exact full run. They do
not yet admit GPU launch, a complete copied SDK, resources or protected ASR.
