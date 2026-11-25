# Impact Map

Actual map: studio-execution-map-983b77f-20261007/serena-map.json under
C:/Users/Wareen/AppData/Local/HawEditEvidence. Seven mapped existing symbols.

| Boundary | Existing callers | Verification |
| --- | --- | --- |
| GenerationRequest.from_payload / prepare_generation / _parse / ProducerSelection.argv | web refusal/preparation, generation/submission/queue/runtime/storage/intake tests | complete test_studio_generation.py, test_studio_submissions.py, test_studio_queue.py |
| SubmissionStore.get / work_dir / reserve | queue reconciliation; owned runtime/admission; bounded intake; storage tests | complete test_studio_runtime.py, test_studio_admission.py, test_studio_intake.py, test_studio_storage.py |
| New prepare_studio_execution | new native reconstruction regressions; future protected worker only | complete test_studio_execution_input.py plus test_claims.py |

No existing public signature, schema, producer or HTTP behavior changes. New helper
must use actual persisted private outbox/upload state, not a constructed receipt.
Shared parser composition does not prove inference, billing or publication.
