# Plan — Test-Quality Floor (`specs/test-quality-floor`)

Approved-by: Hawa

## Executive Summary
Implement Task T1.11 from `specs/pro-grade-program/tasks.md`:
1. Enforce zero skipped tests (`skipped == 0`) across ALL test files in CI, closing Threat 6 (`skipif` on critical tests).
2. Add a coverage gate on `src/hawedit/{render,reframe,captions,boundary,clip,delivery,measure}.py` ratcheted at the measured current value via `scripts/coverage.floor`.
3. Provide Proof A: `test_the_gate_refuses_any_skipped_test` in `tests/test_gate_evidence.py`.

---

## Technical Architecture & Implementation Details

### 1. Zero-Skip Enforcement (`src/hawedit/gate.py` & `.github/workflows/gate.yml`)
- Update `check_test_evidence(report_path: Path, *, floor_path: Path, not_before: float | None = None, require_no_skips: bool = False)`:
  - When `require_no_skips=True` and `evidence.skipped > 0`:
    `raise NoTestEvidence(f"{report_path} says {evidence.skipped} test(s) skipped — skipped tests are refused under the zero-skip policy.")`
- Update `main(argv)`:
  - Parse `--require-no-skips` flag.
- Update `.github/workflows/gate.yml`:
  - Pass `--require-no-skips` to `hawedit.gate` in CI jobs (`python-312-compat` and `gate`).

### 2. Coverage Measurement & Ratchet Floor (`src/hawedit/gate.py` & `scripts/coverage.floor`)
- Target modules:
  `src/hawedit/render.py`
  `src/hawedit/reframe.py`
  `src/hawedit/captions.py`
  `src/hawedit/boundary.py`
  `src/hawedit/clip.py`
  `src/hawedit/delivery.py`
  `src/hawedit/measure.py`
- Executable statement baseline:
  - Using CPython bytecode line extraction `co.co_lines()`.
- Ratchet floor file:
  - `scripts/coverage.floor` storing the minimum acceptable covered statement count.
- In `src/hawedit/gate.py`:
  - `check_coverage_evidence(coverage_report_path: Path, floor_path: Path, not_before: float | None = None) -> CoverageEvidence`
  - When `evidence.covered < floor`:
    `raise NoTestEvidence(...)`
  - When `evidence.covered > floor`:
    `write_floor(floor_path, evidence.covered)`
- In `scripts/verify.sh`:
  - Include coverage check in the gate verification step.

### 3. Unit Tests (`tests/test_gate_evidence.py`)
- Implement Proof A: `test_the_gate_refuses_any_skipped_test`:
  - Asserts `check_test_evidence` with `require_no_skips=True` raises `NoTestEvidence` on `skipped > 0`.
  - Asserts `check_test_evidence` with `require_no_skips=False` retains existing backward compatibility.
  - Asserts CLI `python -m hawedit.gate` with `--require-no-skips` exits non-zero and prints refusal on `skipped > 0`.
- Implement coverage gate tests:
  - `test_the_gate_refuses_coverage_below_floor`
  - `test_the_coverage_floor_ratchets_on_growth`
  - `test_the_projects_own_coverage_floor_is_committed`

---

## Verification Plan
1. Create `.codystem-allow-self-edit`.
2. Run `bash scripts/verify.sh --fast` (lint + typecheck).
3. Run target unit tests in `tests/test_gate_evidence.py`.
4. Run full `bash scripts/verify.sh` to confirm full gate passes.
5. Remove `.codystem-allow-self-edit`.
6. Flip ledger via `scripts/update-ledger.sh test-quality-floor T1`.
7. Update `specs/pro-grade-program/tasks.md` row T1.11 to DONE.
