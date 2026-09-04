# Plan — Run Cost Accounting (`specs/run-cost-accounting`)

Approved-by: Hawa

## Objective
Implement Task T0.6 from `specs/pro-grade-program/tasks.md`:
"Record run cost. Every billed call: model, counted tokens, USD estimate (labelled so), in the run report and events. Sum per run."

## Technical Approach
1. **Define `BilledCall` in `src/hawedit/judge.py`**:
   - Fields: `model: str`, `tokens: int`, `cost_usd_estimate: float`, `stage: str`, `candidate_id: str | None = None`.
   - Invariant validation in `__post_init__` (non-empty model and stage, non-negative tokens and cost).
   - `to_dict()` serialization.
2. **Extend `src/hawedit/events.py`**:
   - Add `RunState.BILLED`.
   - Add optional fields in `RunEvent` with defaults: `model=""`, `tokens=0`, `cost_usd_estimate=0.0`, `candidate_id=""`.
   - Add `RunEventLog.billed()` method to emit billed call transitions.
3. **Record Billed Calls in `path_a.py` and `gemini.py`**:
   - `PathADiscovery` records `last_billed_call` upon generating discovery candidates.
   - `GeminiJudge` records `last_billed_call` upon judging candidates.
4. **Integrate into `pipeline.py`**:
   - Add `billed_calls: tuple[BilledCall, ...] = ()` to `PipelineRun`.
   - Collect billed calls from Path A and Stage 4 loops.
   - Emit `log.billed(...)` events.
   - Add `"billed_calls"`, `"total_cost_usd_estimate"`, `"total_tokens_billed"` to `PipelineRun.to_dict()`.
   - Print cost and token summary in the human-readable CLI report.
5. **Testing & Verification**:
   - Implement `tests/test_run_cost.py` with `test_every_billed_call_is_in_the_run_report`.
   - Verify with fast gate, clean commit, full gate, and ledger flip.
