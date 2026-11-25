---
commit: 86f9c12e6ca52fd8309c2b6c694faeeb9f38c86b
media_sha256: n/a (full regression suite; no inference)
host: HawaPC01 Threadripper3990X Windows26300 CPython3.12.10 WSL6.18.54.1
command: bash scripts/verify.sh
libraries: pytest9.1.1 ruff0.9.6 mypy1.15.0
status: WIP; exit1, two failures retained; no gate/CI pass or ledger promotion
---

# Community-1 Full Gate

Clean frozen source:6408passed/2failed/0errors/0skips,2911.94s pytest.
Lint, strict typecheck409files and format409files pass. Full raw log
C:/Users/Wareen/HawEditGate-86f9c12-20261014.log,
SHA256277283c4b4445129db654b0cd6f10778c2e5882a786dea3e687386bc1e3cb0fb.
Unchanged gate XML copied externally to
C:/Users/Wareen/HawEditGate-86f9c12-20261014.xml,
SHA256bac5b629de32c6562a3b0e5478e693bf6bb88b7033ae0f80644bbe486653836d.

Failures: test_absent_weights_are_refused_by_naming_blocker_four assumed that
the global checkpoint did not exist. Real pinned download invalidated that
test setup; RIFFdummy now reaches genuine PCM refusal. Preserve the exact
BLOCKED.md #4 assertion using an explicitly absent checkpoint and valid mono
16kHz PCM, without changing adapter/validator, deleting downloaded assets or
mocking readiness. Actual three Serena pairs precede that input correction;
whole adapter/checkpoint modules24passed9.00s afterwards. Current-SHA full gate
must still validate the correction. No weakened assertion or skipped test.

Second failure: test_checked_in_policy_binds_current_lock_and_assets_and_closes_report.
Existing independent VEX binds81f6f606... rather than this gate's package
a230703c188b9a34845b730804941ea883675b796afb641f4a5a62a3a214eae7.
It also expired2026-09-08 under BLOCKED #24. No self-renewal/rebinding/waiver.
The new source identity includes the approved integrity metadata, not new model
execution. Actual provisioning evidence remains separate from ASR/reel quality.
