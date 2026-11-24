# Impact map — One command, many reels (a2-one-command-reels)

Serena MCP was unavailable; all callers were mapped via `rg` across `src/`, `tests/`, `DECISIONS.md`, `BLOCKED.md`, and `PROGRESS.md`.

| Symbol / Area Touched | Exact Locations in `src/` | Callers / Tests / Docs Affected |
|---|---|---|
| `WslOmniAsrProducer._runtime`, `resolve_champion_checkpoint`, `create_omni_asr_producer` | `src/hawedit/asr.py:267, 380, 1842, 2015` | `src/hawedit/pipeline.py:5517-5543`, `src/hawedit/models.py`, `src/hawedit/studio_host.py:128`, `tests/test_asr.py`, `tests/test_pipeline.py` |
| `extract_proxy`, `detect_shots`, `ingest` | `src/hawedit/ingest.py:478, 534, 787` | `src/hawedit/pipeline.py` (Stage 0 call), `tests/test_ingest.py`, `tests/test_pipeline.py` |
| `PipelineRun`, `_run_episode_delivery`, `run_pipeline`, `build_parser`, `_build_and_run` | `src/hawedit/pipeline.py:340, 2598, 2812, 4884, 5325-5660` | `src/hawedit/web.py:317` (Studio A4 calls `run_pipeline`), `src/hawedit/durable_workflow.py`, `tests/test_pipeline.py`, `tests/test_episode.py`, `tests/test_cli*.py` |
| `package_digest(src/hawedit)` digest sensitivity (shared with A3) | `src/hawedit/wsl_setup.py:1172`, `security/wsl-asr-vex.json` | Every edit to `src/hawedit/*.py` triggers `tests/test_vex.py:140-163` unless `A3` parks the VEX pin or owner re-pins `REVIEWED_VEX_SOURCE` |
| Shared docs (edited only at implementation merge stage) | `DECISIONS.md` (append `## D-336` at end, past `line 16673`), `PROGRESS.md` (table row), `BLOCKED.md` (cite `#3`, `#21`, `#24`; no new number needed) | Checked by `tests/test_claims.py` and lead merge |

## Cross-Lane Coordination Notes

- **`src/hawedit/pipeline.py` & `DECISIONS.md` / `PROGRESS.md`:** Also touched by Lanes 2–5 later; changes in A2 will stay localized to CLI/runtime defaults, `--output-dir`, and `stage_timings_s` fields, with exact line diffs noted before lead merge.
- **`src/hawedit/web.py:317`:** A4 (`studio_pipeline_runner`) invokes `run_pipeline`; A2's `stage_timings_s` and default producer config directly unblock zero-flag Studio runs cleanly.
- **`B2` (`lane-2`):** B2's clip-scoped ASR will later speed up Stage 1 further; A2 delivers the first 10 real reels on the 40-min 1440p AI episode with exact per-stage timings so B1/B2 have clean real-episode baselines.
