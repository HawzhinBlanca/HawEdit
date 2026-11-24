# Plan — Studio button runs the real pipeline (a4-studio-pipeline-runner)

Read [`research.md`](./research.md) and [`spec.md`](./spec.md) first. Depends on **A2 (`D-336`)**, **A3 (`D-337`)**, and **A5 (`D-339`)** being approved. Proposed ADR: **D-338**.

## Approach

1. **Shared desktop pipeline builder (`A2` parity):**
   - Extract/share a `desktop_pipeline_kwargs(source, work_dir, ...)` builder between `pipeline.py` (A2) and `web.py` (`JobManager._run_job_stages`) so dropping a video in Studio uses the exact same `omni_asr=True`, active `A5` judge + Path A, `auto_select=True`, plain WSL runtime, and `max_clips` (default `5`–`10`, validated up to `10` in `studio_generation.py`) with zero CLI flags required.
   - Maintain single-worker GPU serialization inside `JobManager` (one active GPU pipeline job running at a time, additional requests queued in order in `JobManager`).
2. **Replace hardcoded `503` stub cleanly (`web.py:591, 814`):**
   - In `POST /api/repurpose`, preserve `self._local_write()` Host checks and `GenerationRequest` + `UploadStore` validation (`400` for invalid payloads/server paths).
   - If `HAWEDIT_PROTECTED_STUDIO=1` / `--protected-studio` (`A3`) is enabled, retain `503 studio_runner_unavailable`. Otherwise enqueue in `JOB_MANAGER` and return `202 Accepted` with `{job_id, status: "queued", events_url: f"/api/jobs/{job_id}/events"}`.
   - Update `GET /api/status` to report live `runner_ready=True`, `status` (`"idle"` / `"running"`), `active_job`, and `latest_reel` when in desktop mode.
3. **Live job state, SSE stage streaming, and delivered preview:**
   - Add per-job monotonic stage event buffer + condition variable in `JobManager` fed by `on_event` (`RunEvent`), exposed at `GET /api/jobs/<id>/events` (`Content-Type: text/event-stream`, closing after terminal `completed`/`failed` state).
   - Teach `GET /api/jobs/<id>` to return the live in-memory/persisted job snapshot when active or fall back cleanly to `read_historical_job`.
   - Ensure `_serve_preview` (`web.py:725`) resolves delivered job clip files cleanly (supporting both `review_clips/` and delivered `rendered/*.mp4` inside the validated job root without loosening `studio_artifacts.py` containment checks).
   - Update `studio_ui.py` to open an `EventSource` stream on `/api/jobs/<id>/events` for queued/running jobs (no `setInterval`, preserving `test_studio_ui.py:109`).

## Files and symbols

| File | Symbol | Planned Change |
|---|---|---|
| `src/hawedit/web.py` | `JobManager` (`:71-436`), `do_POST /api/repurpose` (`:580-602`), `do_GET /api/status` (`:807-829`), `do_GET /api/jobs/<id>/events` (new), `_serve_preview` | Enqueue real A2 pipeline jobs (serialized queue), stream SSE events, report `runner_ready=True` unless `--protected-studio`, serve delivered clip previews |
| `src/hawedit/studio_generation.py` | `_option_argv` (`:54-88`), `GenerationRequest` | Permit `max_clips` `1..10`, align argv generation with A2 desktop defaults |
| `src/hawedit/studio_ui.py` | `generate` (`:913`), `readiness` (`:1264`), job watcher | Subscribe to `/api/jobs/<id>/events` via `EventSource` when job is active; refresh clips on completion |
| `tests/test_web.py`, `tests/test_studio_generation.py`, `tests/test_studio_ui.py`, `tests/test_a4_studio_runner.py` | Existing 503 tests + new AC tests | Update 503 assertions to test protected mode (`test_protected_studio_mode_preserves_503_refusal`), add AC1–AC5 tests |
| `DECISIONS.md`, `PROGRESS.md` | New `D-338`, progress row | Record architectural decision |

## Divergence and Risks

- **No divergence from `BLUEPRINT.md` §3/§5.**
- **Existing tests asserting `503 studio_runner_unavailable`:** `tests/test_web.py:78-80`, `tests/test_studio_generation.py:302`, `tests/test_studio_ui.py:87`. These directly test the stub being replaced; per plan they will be re-scoped to `--protected-studio` mode rather than deleted, alongside new tests covering real desktop execution (`mock/stub run_pipeline` in unit tests + 1 real studio upload-to-reels verification on HawaPC01).
- **Large video uploads:** Verified `UploadStore` chunked `PUT /api/uploads/<id>` works for desktop uploads; testing Studio end-to-end with the 5-min 1440p excerpt first before a full episode avoids multi-GB upload overhead during verification.

## Owner Actions

- Batch-approve `A4` (`D-338`) alongside `A2` (`D-336`), `A3` (`D-337`), and `A5` (`D-339`).

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"
