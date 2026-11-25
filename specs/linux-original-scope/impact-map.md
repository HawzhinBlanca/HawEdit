# Impact Map

Baseline81de681; actual current eight-pair Serena map cited in research.md.
Add linux_scope.py only; no existing production symbol changes in this unit.

Future callers requiring separate pre-edit mapping/tests:
- WslOmniAsrProducer.transcribe: actual direct callers in test_asr,
  test_asr_context and test_asr_worker_diagnostics; ASR Protocol dispatch and
  generated source need supplementary rg. Do not adopt timeout-only launch.
- LinuxOwnerChannel: module declarations and generated real tests only.
- run_native: new audit capture and native/control/capability tests; current
  audit use does not authorize model execution or Linux scope completion.
- prepare_studio_execution and OwnedStudioRuntime.await_activation: test
  callers, no inspected production adoption.
- AttemptStore.finish: tests; cannot release exclusion from a descriptive flag.
- RunEventLog.require_persistence: existing log methods/test callers. Preserve
  sticky behavior and later adopt it at effects/results rather than duplicate it.
- SignedStudioTransport._send: actual guarded billing transport constructor;
  raw authorization, event persistence and resource drain are separate checks.

New whole tests/test_linux_scope.py exercises actual Linux/WSL resources and
unsupported-host/invalid-input refusals. Whole native/control/Linux tests and
claims remain required. No fixture/golden/harness/security-policy edits.
README module inventory, PROGRESS WIP row and evidence header accompany the
new module before full claims/gate. No existing behavior is silently enabled.

Runtime cleanup measurement correction: actual Serena map
C:/Users/Wareen/HawEditLinuxScopeEntropyBaselineMap-20261009/serena-map.json
finds test_linux_scope_clean_close_releases_owned_not_borrowed_descriptors,
with no static references; pytest discovers it and external retained-runtime
observations reuse DRIVER. Source/HEAD/status unchanged during the map.
An independent retained Python3.12 os.urandom control, with no LinuxScope import,
shows one first-use cached /dev/urandom FD and unchanged second-use identity.
Initialize this unrelated runtime facility before the owned-scope measurement.
Do not close/filter that foreign FD or weaken the exact before/after assertion.
