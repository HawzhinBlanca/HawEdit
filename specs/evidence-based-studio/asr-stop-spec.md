# Production ASR First-Failure EARS

Grounding: BLUEPRINT sections 3, 4.2, 5, 8.1; D-278 resolves D-135/D-223 production
continuation against the later owner canon. Existing historical artifacts stay immutable.

| ID | Criterion | Named Regression |
| --- | --- | --- |
| AS1 | WHEN a production region raises during drafting/alignment, THE producer SHALL halt with bounded region/cause evidence and invoke no later region or validator. | test_native_production_stops_on_first_asr_failure, test_worker_production_stops_on_first_asr_failure |
| AS2 | WHEN selected correction transcription or alignment raises, THE producer SHALL halt before later corrections and publish no canonical success output. | test_native_production_stops_on_first_validator_failure, test_worker_production_stops_on_first_validator_failure |
| AS3 | WHEN production halts, THE exception SHALL preserve original diagnostic results and distinguish missing speech from a rejected correction to already aligned speech. | test_strict_helpers_preserve_diagnostic_inputs_and_failure_kind, test_wsl_worker_retains_canonical_alignment_when_validator_correction_is_infeasible |
| AS4 | WHEN a supplied or cached raw transcript has unresolved regional or correction failures, THE pipeline SHALL preserve raw and report both collections while refusing normalization and all downstream work. | test_pipeline_refuses_unresolved_transcript_evidence, test_pipeline_refuses_reused_unresolved_transcript_without_rewriting |
| AS5 | WHEN damaged raw or a raised ASR failure is refused, THE event stream SHALL emit started then skipped/refused transcription, no transcription completion, visual-window progress or new Stage 1 success checkpoint. | test_pipeline_refuses_unresolved_transcript_evidence, test_pipeline_refuses_reused_unresolved_transcript_without_rewriting, test_pipeline_stops_before_visual_work_after_asr_failure |
| AS6 | WHEN diagnostic accounting is invoked explicitly rather than production, THE helpers SHALL retain all failures and original aligned canonical data under their existing diagnostic contracts. | test_one_unalignable_region_does_not_discard_the_others, test_the_written_transcript_says_which_speech_it_does_not_contain, test_strict_helpers_preserve_diagnostic_inputs_and_failure_kind |
| AS7 | WHEN all production regions and corrections succeed, THE native/WSL interfaces SHALL retain source/adapter/provenance/word-clock/routing contracts. | test_wsl_worker_applies_the_same_validator_routing_contract, test_stage1_routes_the_bottom_quartile_to_the_real_validator_seam, test_producer_refuses_identity_drift_during_inference |

Automated unit/real-fixture tests establish contracts, not canonical model quality.
Real native reference, rendering, independently authenticated review and current security
evidence remain prerequisites for delivery and any 10/10 verdict.
