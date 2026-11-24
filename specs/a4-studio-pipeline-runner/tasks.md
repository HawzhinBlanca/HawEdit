# Tasks ledger — a4-studio-pipeline-runner
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  ADR D-338; enable desktop JobManager pipeline queue on POST /api/repurpose & ready /api/status (retaining 503 only under --protected-studio)   (tests: test_studio_status_reports_ready_in_desktop_mode, test_repurpose_queues_real_pipeline_job_with_zero_flags, test_protected_studio_mode_preserves_503_refusal)
- [x] T2  Add GET /api/jobs/<id>/events SSE stream + live /api/jobs/<id> state + delivered preview resolution   (tests: test_job_events_sse_streams_stage_updates_and_closes_on_terminal_state, test_delivered_studio_clips_serve_verified_preview_and_keep_sse_contract)
- [ ] T3  Verify browser/API Studio submission on 1440p excerpt yields real reels with zero flags   (tests: test_delivered_studio_clips_serve_verified_preview_and_keep_sse_contract)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh on integration branch)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] End-to-end local studio run verified producing playable reel(s)
