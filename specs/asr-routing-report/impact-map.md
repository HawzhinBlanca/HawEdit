# Impact Map

Existing source edits: PipelineRun.to_dict and _print_report, both actually
mapped with their definitions and all references before edits. Only pipeline.py.
scores_from_transcript/run_pipeline/RawTranscript._validate_origins inspected
and mapped, not changed. Existing CLI/durable callers preserve shared semantics.

to_dict37 references: production durable_workflow._run_pipeline_step/payload and
pipeline._run_from_args; whole tests test_pipeline, test_durable, test_events,
test_render_boundary_revision, test_render_caption_revision, test_run_cost.
_print_report8 references: production _run_from_args; tests pipeline/_printed/
escalation reason/brand kit and run_cost/billed report. Map receipts in research.

Four existing test bodies actually mapped, zero direct symbol references each:
test_the_run_report_serializes_to_json;
test_partial_asr_correction_and_routing_records_remain_visible;
test_raw_diagnostics_are_the_reporting_source;
test_the_escalation_line_quotes_a_reason_that_actually_escalated.
Preserve all old computational count/trigger/reason assertions on explicitly
diagnostic summaries; strengthen unknown-original and provenance assertions.
Preserve existing unavailable/gap/correction-only expectations.

New whole test_asr_routing_report module uses existing external adapter doubles
and actual trace/router/reader/report. No acoustic accuracy claim. Whole affected
caller suites/static checks and exact full gate required, not filtered tests.
No production numeric escalation consumer outside these pipeline reports found
by scoped rg of src/scripts. Intentional JSON correction recorded in ADR.

Final guard map refreshed to_dict45 references before further edits, receipt in
research. New callers test_unbound_routing_does_not_infer_policy_triggers and
test_raw_words_without_segment_scores_do_not_claim_zero_replay exercise unknown
trigger categories/threshold and absent score inputs. No additional production
caller or adapter behavior change. Preliminary11-module cohort525passed at
package210542d; do not relabel that receipt as post-guard source evidence.

Current ddf8553 corrective map50675d781b0d5a1a74c5a6139694b9630429e72bc6f641625479a8da9c2151f1:
two existing report tests0refs each, a_transcript136refs, full_run0direct refs
(pytest injection dynamic), serializer47refs. Only the two test bodies and an
unused import change. No shared fixture, golden, source or production caller
changes. Preserve count/threshold/trigger partition checks in new scored-input
cases; strengthen actual absent-input assertions in both existing callers.
