# Provisional implementation impact map

Read-only `rg` + direct-source mapping, SHA `532e6efb1708e8dc2c3d14dde4fb7927f5115006`. Serena was not available. Before editing, perform required semantic symbol/reference mapping and expand this map. No application source was changed in this audit.

| Change area | Confirmed producers/consumers | Required cross-boundary checks |
|---|---|---|
| Job identity and lifecycle | `HawEditWebHandler.do_POST`, `JobManager.submit_job`, `_run_job_stages`, `get_job`, `/api/status`, browser `pollJob`, `switchClip` | UI/API, queue durability, failed/restarted jobs, distinct source outputs |
| Pipeline assembly | `_prepare_selection` → `run_pipeline` → `_raw_text_for_words`, boundary fusion, original-source judge slices, `render_clip`; standalone `assemble_spans` and `render_assembled_reel` | Retained word IDs, both timelines, clip IDs, VAD/shot/diarization remapping, exact rendered audio/video/captions |
| Authoritative plan | `VisualEditPlan`, `SourceTimeMapping`, `EffectiveConfiguration`; current construction after `bundle.publish` | Plan generated before render, all output consumers use same version, round-trip provenance, silence tightening and reorder support |
| Publication | `ArtifactBundle` suffix set and `publish`, pipeline review/final branch, `promote_candidate`, `Delivery.to_dict`, no-overwrite guards | Mandatory plan in staging/manifest; write/rename failure; final state after crash; review-to-final migration; protected harness authorization |
| Inspection | `generate_critique_windows`, `inspect_rendered_sequence`, `CritiqueInspectionResult.assert_verdict_grounded`, `visual_repair`, `episode_package` | Real observations versus schedule, mandatory source context, hash invalidation, repair reinspection and actual pipeline call |
| Face check | `check_face_presence`, sanity report callers, tracker/crop planning | Missing resources, empty schedule, full shot coverage, unknown subject confidence, intentional cutaways |
| Recovery | `is_stage_complete`, `save_stage_checkpoint`, `run_pipeline` Stage 0 resume, `workflow_recovery` helpers | Output hashes, producer/config revisions, dependency invalidation, concurrency and uncertain external outcomes |
| Editorial quality | `condense_multiple_arcs`, `condense_story`, `build_story_map`, Path A discovery/judge, assembly and paper-edit selection | Caller integration, duplicate candidate suppression, cross-topic joins, necessary context and fidelity on held-out sources |

Spec/decision anchors to preserve: BLUEPRINT §2 delivery/QC, §3 stage integration, §4 transcript/captions, §5 boundaries; D-262 assembly integration correction, D-263 atomic delivery reconciliation, D-266 silence tightening, D-271 independent discovery. New dependencies or architectural divergences need a recorded ADR, not a silent implementation change.
