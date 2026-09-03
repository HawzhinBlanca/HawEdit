# Impact Map: Speech Enhancement Chain (Task T3.2)

## 1. Direct Symbols Affected
- `hawedit.render.audio_filter`: Added optional keyword parameter `speech_chain: bool = False`. Pre-pends native speech enhancement filter graph.
- `hawedit.render.measure_audio_loudness`: Added optional keyword parameter `speech_chain: bool = False` to ensure Pass 1 loudness measurement measures the pre-conditioned audio graph.
- `hawedit.render.render_clip`: Passes `speech_chain=deliverable` into `measure_audio_loudness` and `audio_filter`.

## 2. Callers & Dependents
- `hawedit.pipeline.run_pipeline`: Calls `render_clip(..., deliverable=(profile == "production"))`. Automatically inherits speech chain enhancement for production deliverables.
- `tests/test_render.py`: Unit tests for `audio_filter`, `measure_audio_loudness`, and `render_clip`.
- `hawedit.delivery.reconcile_delivery`: Level C reconciliation gate asserts integrated loudness (-14 ± 0.5 LUFS) and True Peak ceiling (≤ -0.9 dBFS). The speech chain feeds directly into linear loudnorm to ensure compliance.
