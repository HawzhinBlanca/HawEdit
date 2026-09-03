# Impact Map — `--profile production` (Task T1.9)

## 1. Symbols Modified
- `hawedit.pipeline.build_parser`
  - Callers: `hawedit.pipeline.main`, `tests/test_cli.py`, `tests/test_pipeline.py`.
  - Impact: Adds `--profile` argument. Existing CLI invocations default to `"default"`.
- `hawedit.pipeline.run_pipeline`
  - Callers: `pipeline.py:main`, `durable_workflow.py`, numerous test fixtures in `tests/test_pipeline.py`, `tests/test_durable.py`, `tests/test_events.py`.
  - Impact: Adds keyword-only parameter `profile: str = "default"`. Fully backwards compatible.
- `hawedit.delivery.reconcile_delivery`
  - Callers: `hawedit.pipeline.run_pipeline`, `tests/test_delivery.py`.
  - Impact: Adds production profile check when `clip.provenance.profile == "production"`.

## 2. Test Plan
- `tests/test_pipeline.py`:
  - `test_the_production_profile_cannot_deliver_with_a_skipped_stage`
  - `test_the_contract_records_the_profile_used`
- `tests/test_delivery.py`:
  - `test_delivery_refuses_production_profile_without_human_review`
