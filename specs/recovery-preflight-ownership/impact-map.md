# Actual Caller Impact

Serena FindSymbolTool/FindReferencingSymbolsTool on clean d942897 completed
2026-10-07T10:57:05UTC. Raw recovery-preflight-map-20261007/serena-map.json;
unchanged src/hawedit/workflow_recovery.py. Definition lines198-224, references
are __all__, tests/test_workflow_recovery.py import and two direct calls in
test_visual_workflow_recovery_preserves_evidence_and_publication_identity.

Change only validate_preflight_resources; public signature stays unchanged.
Existing non-negative integer callers retain valid behavior. ResourceCapacityError
is reused unchanged. New tests cover actual native pre-existing files/hardlinks/
directories, invalid budgets before storage, actual directory-creation refusal
with original cause, successful owned cleanup and insufficient capacity.
No production pipeline/HTTP/DBOS caller exists. No other recovery, billing,
checkpoint or publication function is modified or newly admitted.
