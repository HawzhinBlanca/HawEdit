# Protected Producer Attempt Research

Baseline: c5504ef88e8bca7ac3c8484e2838783d82b867c2, 2026-10-07.
Actual Serena LSP definitions/references: 17 pairs, unchanged watched source, in
`C:/Users/Wareen/AppData/Local/HawEditEvidence/protected-producer-worker-map-20261007/serena-map.json`.
All requested definitions were found. File-level fallback references are retained.

The actual shared producer is pipeline._build_and_run. prepare_studio_execution
currently reconstructs inputs only; SignedStudioTransport has test callers only.
OwnedStudioRuntime owns DBOS machinery, not producer authority. SubmissionStore
schema1 is an immutable dispatch outbox, not an attempt/event journal. RunEventLog
restarts its sequence at1 each invocation. project_events correctly refuses mixed
run IDs and duplicate/nonincreasing sequence. The repaired legacy JSONL reader
does not supply transactional durability or attempt identity.

This unit is the attempt prerequisite of the approved protected worker work,
BLUEPRINT sections2-5, D-274/D-276/D-288. Use existing SQLite/private path controls,
not a broad pipeline rewrite. Preserve original submission/DBOS databases and their
schemas. A distinct colocated private journal holds initial attempts, transactional
event records and explicit outcomes. It is observation, not execution authority.

Recovery must not assume a released Windows parent lease proves a WSL producer
child stopped. Therefore a persisted running attempt is preserved and blocks a
second launch; this unit exposes no automatic retry or billing reconciliation.
Private previews are not publication. No completed state is representable here.
Actual supervisor, runtime/model/owner/governance/billing checks and authenticated
review/export remain required before enabling web generation.

Current native gate remains red on stale VEX evidence. Native GPU profile exists
but lacks pyannote/DBOS; default gate profile is CPU. The full producer is not
ready merely because model status, GPU visibility or a runtime receipt passes.
No paid calls, licence acceptance, reviewer enrollment or 10/10 claim follows.
