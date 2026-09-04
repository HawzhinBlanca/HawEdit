# Research — Run Cost Accounting (`specs/run-cost-accounting`)

## Problem Statement
Task T0.6 in `specs/pro-grade-program/tasks.md`:
"Record run cost. Every billed call: model, counted tokens, USD estimate (labelled so), in the run report and events. Sum per run."
Previously, while `judge.py` defined `USD_PER_MILLION_TOKENS = 2.0` and `estimate_cost_usd()`, pipeline runs did not record billed calls in `PipelineRun` or `PipelineRun.to_dict()`, nor were events emitted when billed calls occurred. Operators had no visibility into total USD spent or token volume per run.

## Affected Components
1. `src/hawedit/judge.py`:
   - Export `BilledCall` dataclass holding `model`, `tokens`, `cost_usd_estimate`, `stage`, `candidate_id`.
   - `estimate_cost_usd` calculates estimated USD cost from token count.
2. `src/hawedit/events.py`:
   - `RunState.BILLED` representing a billed model call.
   - `RunEvent` carrying `model`, `tokens`, `cost_usd_estimate`, `candidate_id`.
   - `RunEventLog.billed()` method to emit billed events.
3. `src/hawedit/path_a.py`:
   - `PathADiscovery` records `last_billed_call` upon generating candidates.
4. `src/hawedit/gemini.py`:
   - `GeminiJudge.judge_with_count()` records `last_billed_call`.
5. `src/hawedit/pipeline.py`:
   - `PipelineRun.billed_calls: tuple[BilledCall, ...] = ()`.
   - `PipelineRun.to_dict()` includes `billed_calls`, `total_cost_usd_estimate`, `total_tokens_billed`.
   - `run_pipeline` collects billed calls from discovery and judge passes, emitting `log.billed(...)` events.
   - Printed run report formats billed summary lines.
