# Plan — Verify `mean_logprob` Semantics (`specs/mean-logprob-semantics`)

Approved-by: Hawa

## Executive Summary
Implement Task T0.5 from `specs/pro-grade-program/tasks.md`:
1. Document the unit of `mean_logprob` as natural logarithm units (nats, $\le 0.0$) in `AsrProvenance`, `SegmentConfidence`, `Clip.to_dict()`, and `asr._mean_aligned_logprob`.
2. Add proof test `test_mean_logprob_is_a_per_token_mean_in_nats` in `tests/test_transcripts.py`.
3. Create `evidence/mean-logprob-semantics.md` documenting the recomputation for ep29 segment 0 and binding the evidence to commit and media hash.

## Technical Changes

### 1. Engine & Contract Documentation
- In `src/hawedit/transcripts.py`:
  Update docstrings on `AsrProvenance` and `SegmentConfidence` explicitly defining `mean_logprob` in nats ($\le 0.0$).
- In `src/hawedit/clip.py`:
  Update `Clip.to_dict` docstring noting `mean_logprob` in nats.
- In `src/hawedit/asr.py`:
  Update `_mean_aligned_logprob` docstring.

### 2. Unit Testing (`tests/test_transcripts.py`)
- Implement `test_mean_logprob_is_a_per_token_mean_in_nats()`:
  - Asserts that `mean_logprob` uses base $e$ (nats), always satisfies $\le 0.0$.
  - Asserts that $\text{conf} = \exp(\text{mean\_logprob})$ maps strictly to $(0, 1.0]$.
  - Recomputes segment logprob from word confidences for synthetic words and verifies exact mathematical identity:
    $$\text{seg\_logprob} = \frac{\sum_i \ln(\text{conf}_i) \cdot \Delta t_i}{\sum_i \Delta t_i}$$
  - Verifies exact arithmetic match against ep29 segment 0 ($418..2654$ ms) with $-7.0829329306560185$ nats.

### 3. Living Evidence (`evidence/mean-logprob-semantics.md`)
- Create standard evidence record with YAML header (`commit:`, `media_sha256:`, `host:`, `command:`, `date:`).
- Record the recomputed value for ep29 segment 0 and the aggregate $-7.15824$ nats across the 1,326 segments.

## Verification Plan
1. Fast checks: `bash scripts/verify.sh --fast`
2. Update VEX if source hash changes.
3. Commit changes.
4. Run full gate: `bash scripts/verify.sh`
5. Flip ledger: `bash scripts/update-ledger.sh mean-logprob-semantics T1`
6. Update `specs/pro-grade-program/tasks.md` row T0.5.
