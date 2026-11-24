# Impact Map — `human-grade-director-v2`

| Module / File | Symbols Modified | Callers / Tests Checked | Backwards Compatibility |
| --- | --- | --- | --- |
| `src/hawedit/render.py` | `SPEECH_CHAIN_FILTERS`, `crop_filter()`, `render_clip()`, new `content_aware_push_schedule()` | `pipeline.py`, `tests/test_render.py` (`test_audio_filter_speech_chain` checks `.startswith(SPEECH_CHAIN_FILTERS)`), `tests/test_c10_pipeline_integration.py` | `two_pass_loudness: bool = False` default preserves existing `deliverable=False` unit tests. |
| `src/hawedit/reframe.py` | `stabilize()`, `OpenCvFaceTracker.track()` | `pipeline.py` (lines 1800, 1910), `tests/test_reframe.py`, `tests/test_c10_reframe_anything.py` | `edge_guard_px: int | None = None` default keeps existing `stabilize()` tests byte-identical. |
| `src/hawedit/captions.py` | `build_ass()` | `pipeline.py`, `tests/test_captions.py` (`GOLDEN_HOOK_CARD` calls with `face_intervals=None`), `tests/test_broadcast_studio.py` | Face-aware hook card only activates when `face_intervals` is provided; `merge_short_orphans=False` & `excited_intervals_ms=()` defaults preserve all golden renders. |
| `src/hawedit/caption_polish.py` | new `normalize_sorani_digits()`, `polish_clip_sentences()` | `pipeline.py`, `tests/test_c10_caption_polish_and_silence.py` | Preserves 1-to-1 word count and exact CTC `start_ms`/`end_ms`. |
| `src/hawedit/pipeline.py` | `_render_and_package_clip()`, `_stabilize_focus_track()`, `run_pipeline()` | `tests/test_pipeline.py`, `tests/test_c10_pipeline_integration.py` | Preserves CLI defaults & strict fail-stop semantics. |
| `security/wsl-asr-vex.json`, `tests/test_vex.py` | `source_sha256` / `REVIEWED_VEX_SOURCE` hex digest | `tests/test_vex.py` | Re-pinned after `src/hawedit/` merges; dates unchanged. |
