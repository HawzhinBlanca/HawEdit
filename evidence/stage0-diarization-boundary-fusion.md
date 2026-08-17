# Stage 0 diarization and Stage 5 boundary fusion

Date: 2026-08-15

Revision: uncommitted feature branch measurement; the final commit and hosted run are recorded by
the task ledger only after the canonical gate and CI pass.

Blueprint: §3 Stage 0 and Stage 5. Decision: D-240. Blocker retained: `BLOCKED.md` #4.

## What is now executable

- `Diarizer` is an injected least-trusted producer boundary; no model is silently enabled.
- Base ingest survives a declared diarizer operational refusal and downstream transcript
  segmentation continues.
- Live and persisted output both refuse booleans/coercion, non-segments, negative or inverted
  spans, non-printable labels, noncanonical ordering, overlap, and turns beyond the probed media
  duration.
- A successful result records the exact sorted exclusive turns. Empty means the producer ran and
  found none; `None` means it did not produce a result.
- `PipelineRun` reports diarization independently and cannot claim completeness without the
  measured result.
- Stage 5 receives only the turn bounds containing the first and last selected anchor edges. A
  gap contributes no signal.

## Measured checks

On Windows CPython 3.12 in the checkout environment:

```text
tests/test_ingest.py + tests/test_diarization.py
82 passed in 8.43s

tests/test_pipeline.py
205 passed in 75.63s

ruff check
All checks passed

ruff format --check
6 files already formatted

mypy --strict --no-incremental
Success: no issues found in 3 source files
```

The pipeline integration uses the committed 4.162-second media fixture and an injected exclusive
two-turn producer. For the first selected sentence, the measured turn ending at 1,950 ms becomes
the fused out-point with `out_extended_by="speaker_turn_end"`; the previous 200 ms tail would end
at 1,900 ms. This proves the runtime join, not diarization accuracy.

## Deliberately not claimed

- Community-1 was not downloaded or executed.
- No `pyannote.audio` dependency or host lock was added.
- No Kurdish DER or boundary-reconciliation score was measured.
- No face was associated with a speaker identity, and no render is labelled speaker-tracked.
- AC-9 and M1.3 remain partial until gated bytes, licence attribution, real multi-speaker material,
  and human-reviewed crop evidence exist.

## WSL VEX source binding

The source snapshot digest changed because this unit edits `diarization.py`, `ingest.py`, and
`pipeline.py`. The ASR dependency versions, assets, loader controls, worker protocol, model-card
checks, and every advisory disposition are unchanged. The checked-in VEX applicability was
therefore re-bound to package digest
`f2007b91a325d8453a519b32b6ffcb545e5ef81611b8761e07256911d16f1476`; its original
2026-08-09 advisory review and 2026-09-08 expiry remain unchanged rather than being silently
extended by unrelated composition work.
