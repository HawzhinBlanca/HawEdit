# Tasks: Silence Tightening Wired End-to-End (Task T3.3, ADR D-266)

- [x] T1 Extend src/hawedit/silence.py with SilencePlan, plan_silence_tightening, remap_timestamp, and silence_trim_filter with unit tests
- [ ] T2 Update src/hawedit/render.py to splice audio and video according to SilencePlan in render_clip
- [ ] T3 Wire silence tightening into src/hawedit/pipeline.py with --silence-threshold-ms and test reconciliation
