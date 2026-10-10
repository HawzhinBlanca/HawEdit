# Legacy Camera Contract Impact Map

Actual five-pair Serena record and source hashes: research.md.

| Symbol | Actual callers | Proposed change |
| --- | --- | --- |
| test_pipeline_integrates_motion_speaker_tracker_for_active_speaker_reframe | No explicit source references; pytest collection | Correct unsupported positive expectation into explicit preview/production negative controls; keep original failing report. |
| _test_qc | Pipeline fixtures/tests and test_review_candidate_cache callers | No change; preserve all signatures and digest inputs. |
| MOTION_SPEAKER_TRACKED_RENDER_SHA256 | Only the legacy integration test | No change or new expected render hash. |
| MotionSpeakerTracker.track_speakers | Existing constructor/span/no-turn, synthetic-motion, ambiguous hold, listener and scene-reset tests; pipeline protocol dispatch | No source or detector/threshold change; inspect actual evidence, not a mocked speaking result. |
| _resolve_camera | run_pipeline and _render_episode_single_clip | No source change in this extension; preserve strict production admission and explicit preview fallback labels. |

Whole relevant cohorts: pipeline, reframe, candidate framing parity and review
candidate cache, followed by exact clean committed bash scripts/verify.sh. Do not
exclude the original test from any run. No fixtures/goldens/harness edits.
