# Impact Map — Audit Remediation & Polish

## Affected Modules & Callers

### 1. `render.py`
- Symbols: `render_clip`, `_interpolated`, `crop_filter`
- Callers:
  - `hawedit.pipeline.run_pipeline`
  - `tests.test_render`
  - `tests.test_reframe`
- Verification: `pytest tests/test_render.py tests/test_reframe.py`

### 2. Encapsulation Exports
- `boundary.py`: `strict_bool`, `json_object_fields`
  - Callers: `hawedit.judge`
- `clip.py`: `sv6d_from_json`
  - Callers: `hawedit.judge`
- `proposals.py`: `interactive_confirm`
  - Callers: `hawedit.promotion`, `hawedit.workflow_control`
- `pipeline.py`: `proxy_dimensions`, `build_and_run`, `BUILD_ERRORS`
  - Callers: `hawedit.proposals`, `hawedit.durable`, `hawedit.durable_workflow`
- `wsl_setup.py`: `publish_runtime_candidate`
  - Callers: inline setup script in `wsl_setup.py`
- Verification: `ruff check`, `mypy`, `pytest tests/test_judge.py tests/test_proposals.py tests/test_durable.py tests/test_durable_workflow.py`

### 3. `gemini.py`
- Symbol: `GeminiJudge.judge_with_count`
- Verification: `pytest tests/test_gemini.py`
