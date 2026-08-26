# Tasks ledger — judge-top-n
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  Split `_automatic_sentence_selection` into a per-candidate
          `_sentence_run_for_candidate` plus the caller's loop. Pure refactor, behaviour
          identical.                (tests: test_the_selector_returns_a_run_for_one_candidate,
                                            test_auto_selection_still_picks_what_it_picked_before)

- [x] T2  Judge up to N candidates, skipping ineligible ones before any billed call; persist
          each verdict as it arrives.
                                    (tests: test_more_than_one_candidate_can_be_judged,
                                            test_an_ineligible_candidate_costs_no_billed_call,
                                            test_every_verdict_is_persisted_even_when_render_is_refused)

- [ ] T3  Ship the best passing verdict by hook score; refuse with every score named when none
          passes.                   (tests: test_the_best_passing_candidate_wins_not_the_first,
                                            test_no_passing_candidate_refuses_and_names_every_score)

- [ ] T4  `--judge-top-n` on the parser and `_build_and_run`; N=1 reproduces today exactly.
                                    (tests: test_judge_top_n_defaults_and_is_bounded,
                                            test_n_of_one_is_todays_behaviour)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
- [ ] D-253 still refuses at the artifact boundary — selection does not exempt a clip
