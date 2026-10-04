# Impact map

Baseline: `7fa7d3a37efb8f11d68ecc2b9a52ecd082f7535e`.
Actual headless Serena LSP definitions and references, not rg-only mapping:
`C:/Users/Wareen/HawEditQuality-7fa7-20261004/framing-impact-map.json`.
Seven queries completed; mapped source hashes and repository status unchanged.
Zero-based Serena locations must be converted before user-facing line links.

| Symbol | Direct referencing locations | Proposed treatment |
|---|---:|---|
| `_render_episode_single_clip` | 1, `_run_episode_delivery` | Replace ignored-policy tracking block with shared resolution |
| `_run_episode_delivery` | 3, `run_pipeline` | Preserve per-candidate refusal, private review and item state |
| `run_pipeline` | 195 | Preserve API; extract only camera resolution needed for parity |
| `validate_speaker_focus_points` | 17 | Reuse; no validator weakening |
| `layout_policy` | 12 | Reuse; no new motion algorithm or accuracy claim |
| `MotionSpeakerTracker.track_speakers` | 12 | No model/algorithm change; labelled performance remains unknown |
| `render_clip` | 63 | No signature/encoder/filter redesign; verify passed crop evidence |

`run_pipeline` references include `_build_and_run`, web entry points, and tests for
ASR halt, checkpoints, episode orchestration, events, ingest cache, pipeline,
boundary/caption revision, review findings, cost and screening. Camera validators
also have diarization acceptance callers. Renderer callers include proposals and
the two custom demonstration scripts as well as pipeline/render tests.

Static references do not enumerate every runtime protocol dispatch or external
consumer. In particular, the tracker is called through a protocol and one existing
branch casts it to Any. Keep the public signatures unchanged and exercise both
actual pipeline branches, not only a new helper. Before editing any additional
existing symbol, extend its actual definition/reference map.

Caller regression modules after approval: complete `test_pipeline`, `test_episode`,
`test_reframe`, `test_studio_generation`, `test_pro_video_repurpose`, `test_render`,
`test_render_boundary_revision`, `test_render_caption_revision`, `test_events`,
`test_checkpoint`, `test_ingest_cache`, `test_review_findings`, `test_run_cost`,
`test_screener`, and `test_asr_stop`. Exact full gate remains mandatory, regardless
of focused caller results. No selection/deselection to disguise failing cases.

Implementation adds `test_candidate_framing_parity` as a direct `run_pipeline`
caller. New private `_CameraResolution`, `_accepts_shot_cuts` and `_resolve_camera`
serve only the two existing rendering routes. Public signatures are unchanged.
No existing tracking/layout validator or renderer symbol is modified. The plan
retains all legacy caller assertions, including diagnostic-only empty association.
