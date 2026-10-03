# Bounded Intake Impact Map

Fresh actual Serena definitions/references at cleanbfc210e are preserved before edits.

| Symbol | References | Callers and complete required diagnostics |
|---|---:|---|
| SubmissionStore.pending | 17 | Submission/token/conflict/ack/storage tests; queue serial, lost-ack and restart tests; scripts/studio_research/storage_adoption_posix_probe.py. Existing no-argument list return preserved under budget; overflow becomes explicit refusal |
| SubmissionStore._select | 2 | _get and pending; every selected string/numeric scalar bounded without repairing invalid records |
| SubmissionStore._decode | 2 | _get and pending; retain existing snapshot/hash/state/timestamp checks, no old assertion weakened |
| SubmissionStore._get | 5 | get/reserve/dispatch updates; complete submission and storage caller modules |
| SubmissionStore.get | 10 | Queue reconciliation, scoped work directories and tests; complete queue and generation modules |

New private bounded reader and additive exact-ID recovery_snapshot have no former callers.
Public pending retains list[StoredSubmission]; recovery_snapshot returns an immutable tuple
in requested ID order and refuses duplicate/missing IDs rather than silently omitting work.
No DBOS getter/deserializer, producer, billing or HTTP execution is called by these reads.
Complete test_studio_intake.py,test_studio_submissions.py,test_studio_storage.py,
test_studio_queue.py,test_studio_generation.py are required, then the exact clean full gate.
