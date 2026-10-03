# Raw Admission Impact

New studio_admission API consumes PrivateSqlitePath.verify (21 existing references), passed
binding path and SubmissionStore.recovery_snapshot (five). StoredSubmission (13 references)
is used unchanged. Constructor's zero explicit Serena references is recorded, not interpreted
as unused; this new reader does not construct/recreate a journal. Actual definitions/references
are in raw-admission-before-map.json. No existing signatures, queue/CLI/server behavior change.

Affected verification: new test_studio_admission plus complete studio_intake/submissions/
storage/queue/generation modules and evidence-based-studio documentation/claims inventory.
Actual DBOS publisher migration used only by tests; production imports no DBOS/ORM/pickle.
Next engine/lease/bootstrap/worker unit must map its actual existing callers before edits.
Fresh pre-correction maps: raw-admission-correction-map.json (_validate1/1,_projection1/1,
_read1/2,inspector1/21 including file-level test import), raw-admission-policy-map.json
(_policy1/1,_validate1/1), raw-admission-attributes-map.json (_validate1/1). Complete caller
modules retained for each correction; new positive and refusal tests do not relax prior cases.
