# Research — Studio button runs the real pipeline (a4-studio-pipeline-runner)

Date: 2026-11-18. Host: `HawaPC01`, commit `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf`. Serena MCP was unavailable; callers mapped via `rg` and direct inspection.

## 1. Current Stubs & Existing Infrastructure

1. **Hardcoded HTTP 503 stub (`src/hawedit/web.py:580-597, 807-829`):**
   - `POST /api/repurpose` validates `GenerationRequest.from_payload()` and `request.validate_source(_upload_store())`, then immediately responds `503` with `{"code": "studio_runner_unavailable", "error": "Source validated. The durable studio runner and owner-authorized producer configuration are not connected yet; no job was queued."}`.
   - `GET /api/status` unconditionally returns `{"status": "unavailable", "runner_ready": False, "code": "studio_runner_unavailable", "active_job": None, "latest_reel": None, ...}`.
2. **Existing usable worker (`src/hawedit/web.py:71-436`):**
   - `JobManager` already persists `job.json`, tracks `status`/`stage`/`stage_index`/`progress_percent` via `on_event`, invokes `hawedit.pipeline.run_pipeline(**pipeline_kwargs)` on a background thread (`_run_job_stages` at `web.py:249-432`), extracts `episode_manifest.clips` / `Delivery` / `RenderResult` clips, and marks failed/skipped stages truthfully.
   - However, `web.py:291-317` passes `auto_select=True` **without** enabling canonical OmniASR (`omni_asr=True`), Path A/Stage 4 (`gemini=True`), or the A2/A3 plain WSL desktop runtime defaults — so running it directly today would stop at Stage 1 (`SKIPPED transcript`).
3. **Existing UI & preview seams (`src/hawedit/studio_ui.py`, `web.py:725-805`):**
   - `studio_ui.py:1264-1291` already polls `GET /api/status` on load and enables the UI when `result.runner_ready === true`.
   - `studio_ui.py:913-925` already `POST`s `GenerationRequest` to `/api/repurpose` and refreshes the selected `job_id`.
   - `web.py:725-737` already routes `GET /api/jobs/<id>/clips/<clip_id>/preview` -> `_serve_preview(...)`.
   - Gaps: (a) no `GET /api/jobs/<id>/events` SSE endpoint for live stage streaming without `setInterval` (`tests/test_studio_ui.py:109` asserts `"setInterval" not in DASHBOARD_HTML`); (b) `studio_generation.py:84` restricts `max_clips` to `{1, 2, 3, 5}` instead of `1..10`; (c) `GET /api/jobs/<id>` (`web.py:793-805`) only calls `read_historical_job`, without checking live `JOB_MANAGER` status/events cleanly; (d) `tests/test_web.py:78-80`, `tests/test_studio_generation.py:302`, and `tests/test_studio_ui.py:87` pin today's 503 stub.

Answers to: `BLUEPRINT.md` §3, §5; Task Sheet `A4`, `A3` (`D-337`); proposes **D-338**.
