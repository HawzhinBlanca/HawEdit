# Tasks ledger — harness-integrity
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.
#
# This is the first specs/<feature>/tasks.md this repository has ever had. Until it existed,
# scripts/update-ledger.sh:41-44 refused every invocation for want of a target, which is why
# AGENTS.md's "only update-ledger.sh flips a row" had never once been true.

- [x] T1  Sandbox helper + argument-shape refusals of the ledger flipper   (tests: test_the_ledger_flipper_refuses_fewer_than_three_arguments, test_the_ledger_flipper_refuses_a_task_id_outside_the_allowed_set, test_the_ledger_flipper_refuses_a_citation_that_is_not_a_plain_test_name)
- [x] T2  Ledger and row refusals, and proof no refusal reaches the gate   (tests: test_the_ledger_flipper_refuses_a_feature_with_no_ledger, test_the_ledger_flipper_refuses_a_task_id_with_no_row, test_the_ledger_flipper_does_not_prefix_match_a_longer_task_id, test_the_ledger_flipper_short_circuits_a_row_already_marked_done, test_no_refusal_path_reaches_the_gate)
- [x] T3  The Stop hook's exit-code map and its already-active short circuit   (tests: test_the_stop_hook_maps_every_gate_exit_code, test_the_stop_hook_lets_go_when_it_is_already_active)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] scripts/test-count.floor committed in the same commit as the tests, not hand-edited
      (.github/workflows/gate.yml:126-127 fails a run that ratcheted it)
- [ ] Every row above flipped by scripts/update-ledger.sh itself, never by hand — this is the
      end-to-end proof that the flipper works, and the half pytest cannot reach
- [ ] specs/harness-integrity/ledger.log exists and carries one provenance line per flipped row
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
- [ ] D-NNN written in DECISIONS.md closing the deferral D-198:10265-10272 recorded, naming what
      stayed structurally untestable and why
