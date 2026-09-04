# Impact Map — Test-Quality Floor (`specs/test-quality-floor`)

## Modified Files
1. `src/hawedit/gate.py`
   - Role: Gate evidence grader and floor manager.
   - Changes:
     - Add `CoverageEvidence` dataclass to track covered statements per target module.
     - Add `TARGET_COVERAGE_MODULES: Final = ("boundary.py", "captions.py", "clip.py", "delivery.py", "measure.py", "reframe.py", "render.py")`.
     - Update `check_test_evidence()` to accept `require_no_skips: bool = False`. If `require_no_skips` and `evidence.skipped > 0`, raise `NoTestEvidence`.
     - Add `check_coverage_evidence()` or integrated coverage floor evaluation against `scripts/coverage.floor`.
     - Update `main(argv)` CLI to accept `--require-no-skips`, `--coverage-floor <path>`, and `--coverage-report <path>`.
   - Callers affected:
     - `tests/test_gate_evidence.py`
     - `tests/test_review_findings.py`
     - `scripts/verify.sh`
     - `.github/workflows/gate.yml`

2. `scripts/verify.sh`
   - Role: Canonical gate runner.
   - Changes:
     - Add `COVERAGE_FLOOR="$here/scripts/coverage.floor"`.
     - Add `COVERAGE_REPORT="$here/.gate/coverage-report.json"`.
     - In `run_step "test evidence"`, pass coverage floor and report arguments to `hawedit.gate`.

3. `.github/workflows/gate.yml`
   - Role: GitHub Actions CI gate of record.
   - Changes:
     - In `gate` job, invoke `hawedit.gate` with `--require-no-skips`.
     - In `gate` job, verify `git diff --exit-code -- scripts/coverage.floor`.

4. `tests/test_gate_evidence.py`
   - Role: Tests for gate evidence checking.
   - Changes:
     - Implement Proof A: `test_the_gate_refuses_any_skipped_test`.
     - Add tests for coverage floor verification and ratcheting.

5. `scripts/coverage.floor`
   - Role: Committed floor holding the minimum acceptable covered statements across the 7 target files.
   - Value: Measured current value.

6. `specs/pro-grade-program/tasks.md`
   - Role: Program task ledger.
   - Mark T1.11 DONE once verified with cryptographic evidence.
