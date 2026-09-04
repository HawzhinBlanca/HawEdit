# Research — Test-Quality Floor (`specs/test-quality-floor`)

## 1. Problem Statement
Task T1.11 from `specs/pro-grade-program/tasks.md`:
> "Add a coverage gate on `src/hawedit/{render,reframe,captions,boundary,clip,delivery,measure}.py` at the measured current value (ratchet-only, like the count floor) and a CI `skipped==0` check across **all** test files, not only `test_ingest.py`. Requires `.codystem-allow-self-edit`. Proof required: A: `test_the_gate_refuses_any_skipped_test`. E: CI job."

### Threat Model (Threat 6)
From `specs/pro-grade-program/research.md` §7.7:
> "6. A `skipif` on an awkward media test plus one trivial test."

Previously:
- `scripts/verify.sh` runs `pytest --junitxml=$TEST_REPORT` and then grades `.gate/last-test-run.xml` using `hawedit.gate`.
- `hawedit.gate` guards against `passed == 0`, `collected == 0`, `failures > 0`, `errors > 0`, and `passed < floor`.
- However, if a developer added `@pytest.mark.skipif(...)` on critical media tests, `hawedit.gate` in its default configuration allowed `skipped > 0` as long as `passed >= floor`.
- In `.github/workflows/gate.yml`, CI explicitly guarded against skips in only two files:
  - `tests/test_captions.py` (`golden_reference or simple_shaping`)
  - `tests/test_ingest.py`
- All other 109 test files in CI had no zero-skip requirement, creating a potential hole where tests could silently skip on missing host dependencies or broken conditions.

### Coverage Floor Requirement
- The core media and packaging pipeline consists of 7 files in `src/hawedit/`:
  1. `render.py` (FFmpeg filtergraph assembly, video encoding, loudnorm, punch-ins)
  2. `reframe.py` (9:16 vertical cropping, speaker tracking, subject framing)
  3. `captions.py` (ASS generation, Kurdish RTL complex shaping, font validation, karaoke timing)
  4. `boundary.py` (in/out anchor fusion, Kurdish sentence invariant #2, soft boundary clamping)
  5. `clip.py` (clip data model, editorial contracts, QC verification, assert_renderable)
  6. `delivery.py` (artifact bundle publication, checksums, atomic write-once directory layout)
  7. `measure.py` (perceptual evaluation, audio/visual measurement, verification metrics)
- Neither `pytest-cov` nor `coverage` is installed in the locked `.venv` (per `pyproject.toml` and `requirements/host-gate-*.txt`). Modifying third-party dependencies would invalidate the locked gate profile.
- A coverage solution must be zero-dependency, standard-library based, deterministic, and fast across both Linux and Windows.

---

## 2. Real Code & Architecture Analysis

### 2.1 `src/hawedit/gate.py`
`gate.py` parses `.gate/last-test-run.xml` to extract:
```python
TestEvidence(collected=..., skipped=..., failures=..., errors=...)
```
and checks against `floor_path` (`scripts/test-count.floor`).
To enforce zero skips:
- Add `require_no_skips: bool = False` to `check_test_evidence()`.
- When `require_no_skips=True` and `evidence.skipped > 0`, raise `NoTestEvidence` citing the exact skipped count.
- Support `--require-no-skips` flag in `main(argv)`.
- In `.github/workflows/gate.yml`, pass `--require-no-skips` during the evidence check step.

### 2.2 Bytecode Line Tracing for the 7 Target Files
Using CPython's native `code.co_lines()` table, we extract the exact executable bytecode statement line numbers for each file and trace execution using a call-filtered `sys.settrace`:
- `render.py`: 751 / 762 lines (98.6%)
- `reframe.py`: 315 / 323 lines (97.5%)
- `captions.py`: 826 / 848 lines (97.4%)
- `boundary.py`: 241 / 250 lines (96.4%)
- `clip.py`: 793 / 846 lines (93.7%)
- `delivery.py`: 346 / 380 lines (91.1%)
- `measure.py`: 453 / 567 lines (79.9%)
Total: **3,725 / 3,976 executable lines (93.7% overall coverage)**.

By using a call-filtered `sys.settrace` handler (`call_tracer`), tracing overhead is restricted strictly to calls within the target files, ignoring all non-target modules and standard library internals.

### 2.3 Coverage Ratchet Floor (`scripts/coverage.floor`)
Like `scripts/test-count.floor`, `scripts/coverage.floor` records the lowest acceptable covered statement count.
- When covered lines `< floor`: gate refuses with `NoTestEvidence`.
- When covered lines `> floor`: gate automatically ratchets the floor upward.
- CI verifies that `git diff --exit-code -- scripts/coverage.floor` is clean, ensuring ratchet updates are committed deliberately.
