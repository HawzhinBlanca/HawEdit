# Strict Stage 1 evidence — impact map

## Symbols and callers

- `transcripts.UnalignedSpeech`
  - produced by `asr.transcribe_prepared_segments`
  - consumed by `RawTranscript`, `PipelineRun.to_dict`, and transcript persistence
- `transcripts.RejectedValidatorCorrection`
  - produced by `asr._validate_hard_segments`
  - consumed by `RawTranscript` and `PipelineRun.to_dict`
- `transcripts.SegmentConfidence`
  - produced by `asr.build_raw_transcript`
  - consumed by `escalation.scores_from_transcript`
- `transcripts.AsrProvenance`
  - produced by Stage 1 and benchmark adapters
  - serialized into raw transcripts and editing JSON
- `RawTranscript.from_json`
  - called by `TranscriptStore.read_raw`, `asr_worker` consumers, WSL bridge output parsing,
    the pipeline CLI's `--transcript`, and tests
- `NormalizedTranscript.from_json`
  - called by `TranscriptStore.read_norm`
- `escalation.SegmentScore`
  - constructed from both live segment results and persisted transcript confidence
  - consumed by `select_for_validation`

## Test coverage required

- `tests/test_transcripts.py`: each invalid type/value, duplicate keys, non-standard constants,
  container/member shapes, reason bounds, and valid round trips.
- `tests/test_escalation.py`: strict public score boundary and unchanged valid decisions.
- `tests/test_pipeline.py`: one supplied malformed transcript produces exit 2 with no traceback
  and never reaches the pipeline.

No model, GPU, network, credential, fixture, golden, gate, or workflow file is affected.
