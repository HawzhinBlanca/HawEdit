# Tasks — Reel Visual Quality

- [x] **T1:** Stop using hand-crafted demo scripts; run baseline on spans through `hawedit.pipeline` with NVENC.
- [x] **T2:** Implement strict fail-stop in `GeminiStoryEvaluator` on missing fields (`StoryCondensationError`). (Verified: `tests/test_condenser.py:test_evaluator_missing_field_raises_fail_stop`)
- [x] **T3:** Implement per-shot adaptive vertical framing and `sendcmd` crop scaling in `render.py` / `reframe.py`. (Verified: `tests/test_render.py:test_crop_filter_switches_scale_and_eye_line_at_shot_cut`, ADR `D-330`)
- [x] **T4:** Upgrade `SanityGate.check_face_presence` to measure face height share & vertical headroom floors. (Verified: `tests/test_sanity_gate.py:test_check_face_presence_fails_on_small_face_height_share`)
- [x] **T5:** Elevate captions to chest level (`margin_v` >= 480px) and enhance hook banner styling. (Verified: `tests/test_captions.py`, `tests/test_broadcast_studio.py`)
- [ ] **T6:** Re-render real clips, run gate verification, and produce per-shot frame contact sheets for review.
