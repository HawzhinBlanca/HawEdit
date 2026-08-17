# Tasks ledger — ledger-id-exactness
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [ ] T1  Escape the dot in the task id at all three row-matching sites   (tests: test_the_ledger_flipper_treats_a_dot_in_a_task_id_as_a_literal, test_the_ledger_flipper_still_matches_a_genuinely_dotted_task_id, test_the_ledger_flipper_short_circuits_only_the_literal_dotted_row)
- [ ] T2  Escape the dot in each citation at the report lookup, verified by hand   (tests: test_the_ledger_flipper_treats_a_dot_in_a_task_id_as_a_literal)

# T2 cites T1's test deliberately and it is the weakest row in this repository. The citation
# check runs below update-ledger.sh:78 and pytest cannot reach it, so no test proves T2. The
# cited test only proves the shared escape helper works at a site that IS reachable. Flipping T2
# on that citation is the most honest option available and is still weaker than the rule intends
# — which is itself the argument for the follow-up feature named in impact-map.md.

## Definition of Done (all must be true)
- [ ] Both AC tests pass                      (bash scripts/verify.sh)
- [ ] All 16 existing harness tests still pass — especially the five listed in impact-map.md
- [ ] lint + typecheck + format green         (same gate)
- [ ] The awk program re-run by hand with a dotted id, output recorded — pytest cannot reach it
- [ ] The citation lookup re-run by hand with `test_al.ha` against a report holding `test_alqha`,
      showing it now refuses; output recorded in the ADR
- [ ] `.codystem-allow-self-edit` deleted, and absent from `git status`, before committing
- [ ] scripts/test-count.floor committed in the same commit as the tests, not hand-edited
- [ ] Rows flipped by scripts/update-ledger.sh itself
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] D-199 amended with the fix, both reproductions, and the citation-site severity
