# Impact map — speaker/face association

## Planned source changes

| File | Symbols | Reason |
|---|---|---|
| `src/hawedit/reframe.py` | `FocusPoint`, new speaker-labelled point/protocol/validator | Define and validate the association evidence at one boundary. |
| `src/hawedit/pipeline.py` | `run_pipeline`, Stage 6 tracking block, render call | Pass final overlapping turns, select truthful fallback, and preserve structured failure. |
| `src/hawedit/render.py` | `render_clip` | Accept and validate the explicit reframe provenance attached to the artifact. |

## Planned tests

| File | Coverage |
|---|---|
| `tests/test_reframe.py` | strict point fields, turn/time association, ambiguity, invalid output |
| `tests/test_pipeline.py` | speaker success, face/static fallback, missing diarization, failure reporting, output label |
| `tests/test_render.py` | mode/point consistency and reachable `SPEAKER_TRACKED` artifact |

## Compatibility and non-goals

- The `--face-reframe` CLI remains face-only until a production speaker tracker exists.
- Existing injected `SubjectTracker` implementations keep their three-argument method.
- No new dependency, model, registry entry, threshold, network download, or licence claim is added.
- `BLUEPRINT.md` remains frozen; the implementation follows §3 rather than amending it.
- `PROGRESS.md` and evidence will describe a composed seam, not a measured production feature.
