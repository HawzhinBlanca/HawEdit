# Impact Map — Run Cost Accounting (`specs/run-cost-accounting`)

## Affected Modules & Callers
- `src/hawedit/judge.py`:
  - New export: `BilledCall`.
  - Impact: zero breaking changes.
- `src/hawedit/events.py`:
  - New enum value: `RunState.BILLED`.
  - Extended dataclass: `RunEvent` (optional fields: `model`, `tokens`, `cost_usd_estimate`, `candidate_id`).
  - Extended logger: `RunEventLog.billed()`.
  - Serialization: `JsonlEventSink` and `read_events`.
  - Impact: backward-compatible default parameters preserve all existing callers.
- `src/hawedit/path_a.py`:
  - `PathADiscovery`: records `last_billed_call`.
- `src/hawedit/gemini.py`:
  - `GeminiJudge`: records `last_billed_call`.
- `src/hawedit/pipeline.py`:
  - `PipelineRun`: new field `billed_calls: tuple[BilledCall, ...] = ()`.
  - `PipelineRun.to_dict()`: includes `"billed_calls"`, `"total_cost_usd_estimate"`, `"total_tokens_billed"`.
  - `run_pipeline`: collects calls and emits events.
  - Printed report: includes billed summary line if `run.billed_calls` is non-empty.
- Tests:
  - `tests/test_run_cost.py`: comprehensive test suite asserting `test_every_billed_call_is_in_the_run_report`, invariant validation, and event ledger roundtrip.
