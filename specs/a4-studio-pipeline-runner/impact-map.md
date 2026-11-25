# Impact map — Studio button runs the real pipeline (a4-studio-pipeline-runner)

Serena MCP was unavailable; callers mapped via `rg` across `src/` and `tests/`.

| Symbol / Route Touched | Exact Locations in `src/` | Callers / Tests Affected |
|---|---|---|
| `POST /api/repurpose` & `503 studio_runner_unavailable` | `src/hawedit/web.py:580-602` | `src/hawedit/studio_ui.py:913,926`, `tests/test_studio_generation.py:295-307`, `tests/test_web.py:84-129,482`, `tests/test_robustness_audit.py:82`, `tests/test_studio_history.py:466`, `tests/test_studio_storage.py:314` |
| `GET /api/status` | `src/hawedit/web.py:807-829` | `src/hawedit/studio_ui.py:1269`, `tests/test_web.py:72-82`, `tests/test_studio_artifacts.py:200,388,410`, `tests/test_studio_history.py:378,388` |
| `JobManager._run_job_stages` | `src/hawedit/web.py:249-432` | Calls `hawedit.pipeline.run_pipeline` (`web.py:317`); must use same producer defaults as `A2` (`src/hawedit/pipeline.py:5517+`) |
| `GET /api/jobs/<id>` & `_serve_preview` | `src/hawedit/web.py:725-737, 793-805` | `src/hawedit/studio_artifacts.py`, `src/hawedit/studio_history.py`, `tests/test_studio_history.py`, `tests/test_studio_artifacts.py` |
| `_option_argv` (`max_clips`) | `src/hawedit/studio_generation.py:54-88` | `src/hawedit/web.py:586`, `tests/test_studio_generation.py`, `tests/test_studio_ui.py:62-92` |
| `DASHBOARD_HTML` | `src/hawedit/studio_ui.py:913-936, 1264-1291` | `tests/test_studio_ui.py:62-120` (note `:109` asserts `"setInterval" not in DASHBOARD_HTML`, so live progress MUST use SSE `EventSource`, not polling timers) |
| Shared docs (only at merge) | `DECISIONS.md` (new `## D-338`), `PROGRESS.md` | Checked by `tests/test_claims.py` |
