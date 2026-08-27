# Tasks ledger — candidate-span
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [ ] T1  ADR for the target range: the owner's numbers, the date, and why it is a decision
          rather than a derivation from §3 (BLUEPRINT states no clip duration).
                                  (tests: test_the_target_range_is_a_named_decision)

- [ ] T2  Path A's prompt states the range, and the response is measured against it — an
          instruction to a model is a request, not a guarantee.
                                  (tests: test_the_discovery_prompt_states_the_target_duration,
                                          test_span_compliance_is_measured_not_assumed)

- [ ] T3  `_sentence_run_for_candidate` grows a run outward from a seed to the target, on
          complete sentence boundaries only.
                                  (tests: test_a_short_candidate_grows_to_the_target,
                                          test_growth_stops_at_complete_sentence_boundaries,
                                          test_a_candidate_already_in_range_is_left_alone)

- [ ] T4  A candidate that cannot reach the minimum is ineligible with that reason and costs no
          billed call; existing eligibility tests still pass.
                                  (tests: test_a_candidate_that_cannot_reach_the_minimum_is_refused,
                                          test_an_ineligible_candidate_costs_no_billed_call)

- [ ] T5  **Measure it on real footage.** Re-run ep10 and ep01 and record eligibility counts and
          verdict scores before/after in `evidence/`. The hypothesis is that misleading-edit risk
          falls when a fragment becomes an argument; this is where it is confirmed or refuted.
                                  (tests: test_the_measured_span_evidence_is_recorded)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
- [ ] T5's evidence states the before/after honestly, including if the hypothesis was wrong
