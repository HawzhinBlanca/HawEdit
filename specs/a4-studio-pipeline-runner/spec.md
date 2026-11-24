# Spec — Studio button runs the real pipeline (a4-studio-pipeline-runner)

EARS acceptance criteria (`tests/test_a4_studio_runner.py`, `tests/test_web.py`, `tests/test_studio_generation.py`, `tests/test_studio_ui.py`).

- **AC1** WHEN a client requests `GET /api/status` in default desktop mode (without `--protected-studio` / `HAWEDIT_PROTECTED_STUDIO=1`), THE studio server SHALL report `"runner_ready": True`, active queued/running job state when present, and `"status": "ready"` (or `"running"`).
  `test_studio_status_reports_ready_in_desktop_mode`

- **AC2** WHEN an authorized local client submits a valid uploaded `source_id` to `POST /api/repurpose` in default desktop mode, THE studio server SHALL enqueue a real job in `JobManager` invoking the shared A2 pipeline defaults (`omni_asr=True`, active judge/Path A, `auto_select=True`, plain WSL runtime), enforce local Host + non-server-path checks, and return HTTP `202` with `job_id` and `events_url`.
  `test_repurpose_queues_real_pipeline_job_with_zero_flags`

- **AC3** WHEN `--protected-studio` or `HAWEDIT_PROTECTED_STUDIO=1` is set without a connected protected producer host, THE studio server SHALL continue returning HTTP `503` `studio_runner_unavailable` on `POST /api/repurpose` and `"runner_ready": False` on `GET /api/status` (`A3` parity).
  `test_protected_studio_mode_preserves_503_refusal`

- **AC4** WHEN a client subscribes to `GET /api/jobs/<id>/events`, THE studio server SHALL stream `text/event-stream` SSE stage-progress events (`id:`, `event:`, JSON `data:`) in sequence from `JOB_MANAGER` / `RunEvent` logs and terminate cleanly when the job reaches `completed` or `failed`.
  `test_job_events_sse_streams_stage_updates_and_closes_on_terminal_state`

- **AC5** WHEN a Studio job delivers one or more reels, THE dashboard and API SHALL reflect live stage updates via `EventSource` (zero `setInterval`), and `GET /api/jobs/<id>/clips/<clip_id>/preview` SHALL serve the verified `.mp4` within the job sandbox while keeping traversal and symlink refusals active.
  `test_delivered_studio_clips_serve_verified_preview_and_keep_sse_contract`
