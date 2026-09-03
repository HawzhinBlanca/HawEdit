# Implementation Plan: Silence Tightening Wired End-to-End (Task T3.3, ADR D-266)

## Overview
Implement end-to-end media and metadata silence tightening across `src/hawedit/silence.py`, `src/hawedit/render.py`, and `src/hawedit/pipeline.py`.

## Tasks

- [ ] T1: Extend `src/hawedit/silence.py` with `SilencePlan`, `plan_silence_tightening`, `remap_timestamp`, and `silence_trim_filter`. Add unit tests in `tests/test_silence.py`.
- [ ] T2: Update `src/hawedit/render.py` to support `silence_plan` in `render_clip`, trimming/concatenating streams via FFmpeg and checking effective encoded span.
- [ ] T3: Wire `--silence-threshold-ms` into `src/hawedit/pipeline.py`, adjusting clip transcript, ASS generation, punch-ins, focus points, and delivery reconciliation. Add integration test verifying delivery with silence tightening.

Approved-by: user (automated review policy)
