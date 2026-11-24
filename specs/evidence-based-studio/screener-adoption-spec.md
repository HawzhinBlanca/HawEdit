# Screener Adoption EARS

| ID | Requirement | Named regression |
|---|---|---|
| SG1 | WHEN guarded judging and a screener are selected without an explicit screener transport, THE shared builder SHALL refuse before source/model/credential work. | test_shared_builder_refuses_unguarded_screening_before_inputs |
| SG2 | WHEN an explicit request transport is supplied, even a false-valued callable, THE factory/shared builder SHALL preserve and route the selected screener through it without changing the ordinary unguarded CLI or no-screener path. | test_screener_factory_routes_explicit_transport, test_shared_builder_routes_screening_through_explicit_transport, test_explicit_false_valued_screener_transport_never_falls_back |
| SG3 | WHEN Gemini fields are missing, coerced, nonfinite or outside bounds, THE screener SHALL refuse rather than invent scores or Booleans. | test_flash_refuses_unmeasured_or_coerced_scores |
| SG4 | WHEN batch IDs are duplicate, foreign or incomplete, THE screener SHALL refuse instead of claiming comparative ranking for different candidates. | test_flash_refuses_foreign_duplicate_or_incomplete_batch |
| SG5 | WHEN input IDs or top_k are invalid, THE screener SHALL refuse before egress. | test_screeners_refuse_invalid_input_before_egress |
| SG6 | WHEN a legacy Jev response lacks typed legacy fields or instead uses the unsupported current wire, THE codec SHALL refuse contextually without invented/clamped values. | test_jev_refuses_unmeasured_legacy_or_mismatched_wire |
| SG7 | WHEN JSON repeats keys, contains nonfinite values or exceeds response bounds, THE screener SHALL refuse that evidence. | test_screeners_refuse_ambiguous_or_unbounded_json |
| SG8 | WHEN a ScreenedCandidate is constructed, THE record SHALL require real bounded numeric scores, a Boolean decision and valid identity strings. | test_screened_candidate_refuses_coerced_record_fields |

- [ ] SG1-SG8: complete applicable caller tests, exact frozen gate and same-SHA required CI.

Predictions are not human editorial truth, calibrated confidence, authenticated spending or
publication approval. No live TypeSafe/Gemini call or current-wire compatibility is certified.
