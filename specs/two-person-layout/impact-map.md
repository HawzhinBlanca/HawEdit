# Impact Map — Two-Person Split Screen Layout (Task T2.12)

## Modified Symbols

| Symbol | File | Callers Affected | Test Coverage Required |
|---|---|---|---|
| `Reframe.TWO_PERSON_SPLIT` | `src/hawedit/render.py` | `pipeline.py`, `render_clip`, `delivery.py` | Enum value serialization, schema validation |
| `two_person_split_filter` | `src/hawedit/render.py` | `render_clip`, `pipeline.py` | Filter string generation, dimensions validation, vstack syntax |
| `render_clip` | `src/hawedit/render.py` | `pipeline.py`, `tests/test_render.py` | Branching on `Reframe.TWO_PERSON_SPLIT`, FFmpeg execution |
| `detect_rapid_speaker_exchange` | `src/hawedit/reframe.py` | `pipeline.py`, `tests/test_reframe.py` | Turn duration thresholds (< 4s), alternation count, speaker count |
| `compute_two_person_split_crops` | `src/hawedit/reframe.py` | `pipeline.py`, `tests/test_reframe.py` | Bounding box clamping, 9:8 pane aspect ratio, centering on face |
| `run_pipeline` / CLI `--split-screen` | `src/hawedit/pipeline.py` | `__main__.py`, CLI invocation | Option parsing, automatic detection on rapid exchanges, contract provenance |

## Invariants to Preserve
1. **Strict Fail-Stop**: Zero silent fallbacks. If `two_person_split` is requested or triggered but fewer than 2 distinct speakers are tracked, refuse immediately with a clear error.
2. **Standard 1080×1920 Geometry**: Top pane (1080×960) + bottom pane (1080×960) stacked vertically via `vstack=inputs=2` exactly matches the 1080×1920 vertical canvas.
3. **Reconciliation Integrity**: All reconciliation clauses in `delivery.py` (Clause 1 duration, Clause 2 1080×1920 geometry, audio loudnorm) must be completely satisfied.
4. **Gate Green**: All 3,527+ tests must pass without skips (`skipped == 0`).
