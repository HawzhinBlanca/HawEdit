# Spec — One command, many reels (a2-one-command-reels)

EARS acceptance criteria. Each names automated test(s) under `tests/test_a2_one_command_reels.py` (or `tests/test_pipeline.py`) that will verify the requirement once `plan.md` is approved.

- **AC1** WHEN a caller runs `hawedit.pipeline` on a source video without explicit strict-runtime flags on desktop Windows, THE system SHALL resolve the canonical OmniASR producer in plain WSL using configured WSL Python (or discovered `/home/ai/.venv-wsl-whisper/bin/python`) and repo source without failing on a missing `%LOCALAPPDATA%\HawEdit\wsl-asr\<digest>\.ready` receipt.
  `test_default_wsl_runtime_resolves_without_ready_receipt`

- **AC2** WHEN `--strict-runtime` is enabled on `hawedit.pipeline`, THE system SHALL retain the full `load_wsl_runtime_receipt` readiness and digest verification gate rather than weakening it.
  `test_strict_runtime_still_enforces_wsl_receipt`

- **AC3** WHEN `hawedit.pipeline EPISODE.mp4 --work-dir <dir> --reels` (or `--output-dir <reels_dir>`) runs without manual producer flags, THE system SHALL default to multi-clip desktop production mode (champion OmniASR, active judge, `--auto-select`, multi-clip range 5–10, `--ingest-threads 0`, validator off by default) while keeping bare Stage-0 invocations and explicit overrides (`--transcript`, `--verdict`, `--stock-decoder`, `--validate-asr`) untouched.
  `test_cli_default_profile_builds_end_to_end_multi_clip_kwargs`

- **AC4** WHEN Stage 0 extracts a proxy video or runs `detect_shots`, THE system SHALL decode faster than `-threads 1` 4K VP9 CPU bottleneck (supporting configurable threads / proxy-backed shot detection with byte-equivalent `duration_ms` and shot/speech timing preservation on real/synthetic inputs).
  `test_stage0_proxy_threads_and_shot_parity`

- **AC5** WHEN multi-clip episode delivery produces reels (up to `--max-clips`, default 5–10), THE system SHALL export each reel `.mp4` and its sibling `.mp4.measured.json` sidecar atomically to `<output_dir>` (`D:\HawEdit-media\reels\<run>\` when passed) and emit per-stage wall-clock timings (`stage0_s`..`stage6_s`) in `PipelineRun` and JSON output.
  `test_episode_delivery_exports_reels_with_measured_sidecars_and_stage_timings`

- **AC6** WHEN end-to-end verification runs on the 40-minute 1440p AI podcast (`zar-ai-half-episode-lamo`, `CUDA_VISIBLE_DEVICES=0`, `HAWEDIT_MEDIA_ROOT=D:\HawEdit-media`), THE system SHALL produce 10 playable 9:16 vertical `.mp4` reels in `D:\HawEdit-media\reels\<run>\` each paired with `.measured.json`, and record measured wall time per stage in `evidence/`.
  *(Operational milestone — recorded in `evidence/` and verified alongside automated delivery checks `test_episode_delivery_exports_reels_with_measured_sidecars_and_stage_timings`.)*
