# Impact Map

Baseline b8a3a93d48595e1b7430f04f98ca633309e9cd85. Actual read-only Serena
FindSymbolTool/FindReferencingSymbolsTool mapping for eleven adopted/changed symbols:
C:/Users/Wareen/AppData/Local/HawEditEvidence/review-cache-map-b8a3a93-20261007/serena-map.json.

| Symbol | Impact and regression coverage |
| --- | --- |
| pipeline.run_pipeline | Single-clip private recovery only; _build_and_run and legacy web.JobManager._run_job_stages are actual production references. Native tests: test_asr_admission_cache, test_asr_stop, test_candidate_framing_parity, test_checkpoint, test_episode, test_events, test_ingest_cache, test_pipeline, test_render_boundary_revision, test_render_caption_revision, test_review_findings, test_run_cost and test_screener. All retained and included in full gate; no signature change. |
| pipeline._assert_source_unchanged | Existing source-race guard now also brackets retained private-candidate inspection; run_pipeline and episode render callers retain their existing checks. |
| candidate_publication._inspect_media / _measurement_claims | Adopt unchanged bounded decode/measurement and canonical physical comparison, not publication authority. Existing candidate publication tests remain unchanged. |
| candidate_review._snapshot / _json / _canonical | Adopt unchanged bounded private member and typed JSON parsing, duplicate/nonfinite/depth refusal. Existing review tests remain unchanged. |
| studio_private.PrivateDirectory | Reopen candidate leaf without creating or repairing prior storage; existing storage tests unchanged. |
| measure.ClipMeasurement.from_dict | Exact round-trip shape required; actual current decoded observations replace guessed dimensions/duration. Existing measure tests unchanged. |
| edit_plan.VisualEditPlan.from_dict / clip.Clip.from_dict | Exact typed packet plus candidate/source/interval binding. No schema change or sidecar rewriting; existing plan/clip tests unchanged. |

New private cache inspector has run_pipeline as its production caller and real
decoded-media tests as direct callers. No HTTP route, signing/trust enrollment,
producer configuration, paid inference or public-delivery behavior changed.
Map completed 2026-10-07T05:06:07.658981+03:00, eleven actual pairs, adopted
source files unchanged at baseline. SDK processes53760/34252 absent before
session62224 closure. LSP dynamic references supplemented by rg; fallback file
symbols in raw map preserved, not presented as exhaustive static caller proof.

After adoption, two additional actual definition/reference pairs for
inspect_existing_review_candidate and CandidateCacheError confirm run_pipeline
as the only production consumer. Source unchanged during mapping; raw records:
C:/Users/Wareen/AppData/Local/HawEditEvidence/review-cache-adoption-map-20261007/serena-map.json.
SDK processes absent before session47150 closure. Before the nested-object
refinement, four real malformed-block tests produced two expected refusal passes
and two unhandled AttributeError failures; no assertion weakening followed.
