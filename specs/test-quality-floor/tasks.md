# Tasks — Test-Quality Floor (`specs/test-quality-floor`)

| ID | Pri | Task | Proof | Status |
|---|---|---|---|---|
| **T1.11.1** | **P1** | Zero-skip gate enforcement in `hawedit.gate` and CI (`gate.yml`). | A: `test_the_gate_refuses_any_skipped_test`. E: CI job with `--require-no-skips`. | PLANNED |
| **T1.11.2** | **P1** | Core module coverage measurement and ratchet floor in `hawedit.gate` and `scripts/coverage.floor`. | A: `test_the_gate_refuses_coverage_below_floor`, `test_the_coverage_floor_ratchets_on_growth`. | PLANNED |
| **T1.11.3** | **P1** | Harness verification, full gate pass, ledger flip, and program task completion. | `verify.sh` green; ledger updated; T1.11 marked DONE in `pro-grade-program/tasks.md`. | PLANNED |
