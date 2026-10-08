# Caller Impact

Actual Serena maps/hashes and parent identity are in research.md.

| Symbol | Affected Callers | Verification |
|---|---|---|
| studio_generation.ProducerSelection / argv | prepare_generation; tests generation, execution_input, submissions, attempts, queue fixtures | defaults, strict host values, actual route refusals; whole affected modules |
| prepare_generation (unchanged) | studio_execution.prepare_studio_execution; private submission preparation | real uploaded source, asdict configuration and content binding |
| prepare_studio_execution (unchanged) | future protected worker; execution_input tests | reopen actual private stores; exact configuration/argument comparison; drift refusal before work creation |
| Governance.assert_permits_upload / assert_permits_vertex (unchanged) | GeminiJudge / VertexGeminiJudge; new trusted preparation caller | existing actual policy used, not reimplemented or weakened |
| GenerationRequest.from_payload (unchanged) | authenticated web boundary; request tests | all new host fields remain forbidden browser options |

No web worker activation, authorization schema, billing, ASR/model, render,
publication, historical records or dependency-lock changes in this unit.
Old records are not silently rewritten: source/config drift continues to refuse
under D-288; separate migration/recovery reconciliation remains required.
