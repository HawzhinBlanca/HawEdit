# EARS

| ID | Criterion | Named Test |
|---|---|---|
| R1 | WHEN complete validated origins exist, THE report SHALL expose original routing and recorded-original status, independent of selected scores or unbound overrides. | test_recorded_routing_uses_original_trace_not_selected_scores |
| R2 | WHEN legacy origins are absent, THE report SHALL expose null original escalation and explicitly selected-output-replay diagnostics, including zero replay. | test_legacy_routing_is_unknown_even_when_selected_replay_is_zero |
| R3 | WHEN only supplied unbound decisions exist, THE report SHALL retain their counts/reasons as unbound diagnostics without observed routing or policy binding. | test_unbound_routing_is_visible_but_not_observed |
| R4 | WHEN no routing evidence exists, THE report SHALL expose unavailable/null routing rather than measured zero. | test_missing_routing_is_unavailable_not_zero |
| R5 | WHEN validated original inputs route no regions, THE report SHALL distinguish recorded zero from legacy unknown. | test_recorded_zero_is_not_legacy_unknown |
| R6 | WHEN any report serializes, THE report SHALL remain JSON-safe without changing canonical bytes/hash, with shared direct/durable/CLI behavior. | test_routing_report_roundtrips_without_changing_canonical_hash |
| R7 | WHEN the console prints routing, THE report SHALL use JSON's provenance/counts, visibly name unknown originals and pair flagged reasons with their actual subset without claiming human validation. | test_console_routing_matches_json_provenance; test_the_escalation_line_quotes_a_reason_that_actually_escalated |
| R8 | WHEN decisions lack bound original or selected scores, THE report SHALL expose null policy threshold and trigger categories regardless of their reason text. | test_unbound_routing_does_not_infer_policy_triggers |
| R9 | WHEN a legacy raw transcript contains words but no segment scores, THE report SHALL report unavailable routing or supplied unbound diagnostics, never an empty zero replay. | test_raw_words_without_segment_scores_do_not_claim_zero_replay |

Recorded means original-trace self-consistency, not signatures, accurate speech,
model execution, complete production or independent release acceptance.
