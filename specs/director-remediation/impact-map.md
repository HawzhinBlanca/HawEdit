# Impact Map — Director Remediation

## Impacted Files & Symbols

| Module | Symbol / Function | Impact & Callers |
|---|---|---|
| `tests/test_cover.py` | `test_select_cover_frame_on_ep29_extracts_face_thumbnail` | Switches target from uncommitted `work/` to tracked `tests/fixtures/kurdish-speech-3cuts.mp4`, removing `pytest.skip`. |
| `src/hawedit/web.py` | `JobManager.create_job`, `JobManager._run_job_stages`, `HawEditWebHandler.do_GET` | Purges hardcoded `DEFAULT_CLIPS`, `is_ep29`, fake scores, and `/media/ep29` candidate paths. Wires `run_pipeline`. |
| `src/hawedit/captions.py` | `build_ass`, `compute_rtl_word_positions`, `CaptionStyle.RTL_WORD_HIGHLIGHT` | Ensures RTL token order preservation without HarfBuzz run reversal. |
| `src/hawedit/pipeline.py` | `run_pipeline`, `_build_and_run` | Generates `VisualEditPlan` prior to render, integrates critic sequence evaluation, defaults `excise_fillers=True`. |
| `src/hawedit/delivery.py` | `publish_delivery_bundle`, `reconcile_delivery` | Enforces `plan` presence in `ArtifactBundle.suffixes()`, verifies speaking face share threshold. |
| `src/hawedit/silence.py` | `tighten_silence`, `plan_silence_tightening` | Implements repetition (n-gram) and false-start detection. |
| `src/hawedit/measure.py` | `measure_clip`, `ClipMeasurement` | Computes `speaking_face_share` across diarization speech frames. |
