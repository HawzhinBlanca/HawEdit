# Tasks ledger — harness-hardening
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.
#
# Ordered by what each protects. T1 first because it is the only hole CI does not wash out;
# T3 last and alone because it is the one where a mistake makes the gate refuse honest runs.

- [ ] T1  pipefail and an rc check on gate.yml's two anti-skip steps   (tests: test_no_workflow_step_pipes_pytest_without_pipefail)
- [ ] T2  refuse PYTEST_ADDOPTS in verify.sh's existing override loop   (tests: test_the_gate_refuses_an_augmented_pytest)
- [ ] T4  normalise a candidate path before matching it in the guard   (tests: test_the_guard_blocks_native_windows_spellings, test_the_guard_blocks_a_quoted_redirect_target, test_the_guard_refuses_a_write_target_it_cannot_resolve)
- [ ] T3  a run token the gate writes and requires   (tests: test_a_report_without_this_runs_token_is_refused, test_a_report_older_than_the_run_is_still_refused)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] scripts/guard-test.sh still reports 56 checks passed — the T4 regression suite
- [ ] lint + typecheck + format green         (same gate)
- [ ] .codystem-allow-self-edit absent from git status and from every commit
- [ ] scripts/test-count.floor committed in the same commit as the tests it counts
- [ ] Every row above flipped by scripts/update-ledger.sh itself
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] An ADR recording what was closed and what was left open by choice: PYTHONPATH, the
      writing-verb list, the pytest-plugin allowlist, and gate.yml's untested step order
