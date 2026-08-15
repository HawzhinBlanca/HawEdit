# Impact map — speaker-boundary-fusion

## Symbols to change

| Symbol | Current callers | Required coverage |
|---|---|---|
| `ingest.IngestResult` | pipeline, ingest tests, JSON reports | round-trip and strict turn validation |
| `ingest.ingest` | pipeline and ingest tests | unchanged base-ingest behavior |
| new `ingest.attach_diarization` | pipeline | producer success/failure/schema tests |
| `diarization.assert_exclusive` | DER and new attachment/helper | overlap refusal remains shared |
| new `diarization.turn_bounds_for_anchors` | pipeline | containing turn, gap, multi-turn, boundary-edge tests |
| `pipeline.PipelineRun` | CLI JSON/text, completeness tests | skipped/success encoding and completeness |
| `pipeline.run_pipeline` | CLI and pipeline tests | injected producer, failure continuation, Stage 5 fusion |
| `pipeline._print_report` | CLI text tests | measured counts or explicit skip |

## Explicitly unaffected

- `models/sources.json`, `models/revisions.json`, and `models/integrity.json`: no gated bytes are
  approved in this unit.
- `registry.py`: the already-recorded production/control identities do not change.
- `reframe.py` and `render.py`: face tracking remains face tracking until association is designed
  and measured on real multi-speaker footage.
- dependency locks and `pyproject.toml`: no pyannote runtime is introduced in this unit.

## Compatibility risks

- Adding a `PipelineRun` stage changes completeness and report shape. Existing whole-run fixtures
  must explicitly provide measured turns rather than receiving a hidden default.
- `IngestResult.from_dict` is an artifact boundary. It must reject malformed diarization without
  accepting booleans as integers or coercing structured values.
- Turn endpoints use half-open media intervals; anchor-in is contained by
  `start <= anchor_in < end`, while anchor-out is contained by `start < anchor_out <= end`.

