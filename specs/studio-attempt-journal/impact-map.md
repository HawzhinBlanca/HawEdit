# Caller Impact

Actual map provenance is in research.md. Existing symbols are not edited here.

| Symbol | Actual current callers | This unit |
|---|---|---|
| SubmissionStore | studio_admission/execution/queue/runtime; storage probes; admission/execution/intake/queue/runtime/storage/submission tests | New AttemptStore reader uses immutable get; original schema unchanged |
| PrivateSqlitePath | studio_admission/billing/runtime/submissions; private/admission/runtime tests; private journal probe | New distinct journal uses existing identity/ACL/sidecar fences |
| PrivateDirectory | artifact/review/ASR/upload/storage/runtime/web helpers and tests | Existing work-dir owner boundary reused; no helper behavior change |
| project_events | studio_generation and generation tests | AttemptStore projection supplies one validated run/attempt stream |
| prepare_studio_execution | execution module and execution-input tests | No execution authority or new pipeline caller in this unit |
| _build_and_run | pipeline aliases/CLI and content/durable/pipeline tests | Unchanged; genuine worker adoption is next |
| SignedStudioTransport | authorization tests only | Unchanged; never substitute a success flag for raw signature/billing proof |
| OwnedStudioRuntime | runtime module; dynamic subprocess tests | Unchanged; journal is not a supervisor lease |

New automated tests use real private upload bytes, real SQLite transactions,
new interpreter process exit/reopen, actual event values and actual projection.
No models/cloud/DBOS are mocked to claim producer success. Whole affected caller
modules and the canonical full gate remain required; no ledger promotion on red.
