# Research — speaker-boundary-fusion

Parent acceptance program: `specs/true-10-10-acceptance/plan.md`, Phase 5.

## Blueprint and recorded constraints

- `BLUEPRINT.md` §3 selects `pyannote/speaker-diarization-community-1` because its exclusive
  diarization is suitable for transcript-boundary reconciliation. Stage 5 consumes
  `speaker_turn_start` and `speaker_turn_end`; Stage 6 eventually combines diarization with
  face detection.
- `BLOCKED.md` #4 records that Community-1 is gated. Exact authenticated model bytes and a
  production dependency lock are therefore not available evidence in this checkout.
- `DECISIONS.md` D-011 keeps `speaker-diarization-3.1` outside the production registry as a
  benchmark control. No production/control benchmark exists yet.

## Current symbols and callers

Serena is not available in this runtime, so the required symbol and caller mapping was performed
with exact `rg` searches before editing.

- `src/hawedit/ingest.py::ingest` is called by `src/hawedit/pipeline.py::run_pipeline` and the
  ingest tests. It always writes `IngestResult.diarization=None`; there is no producer seam.
- `src/hawedit/ingest.py::IngestResult` already serializes `tuple[Segment, ...] | None`, preserving
  the important distinction between “not run” and “ran and found no turns.”
- `src/hawedit/diarization.py::Segment` and `assert_exclusive` already enforce exclusive turn
  intervals. `boundary_reconciliation` measures distance to aligned word boundaries, but no
  runtime helper selects the turns relevant to a chosen clip.
- `src/hawedit/boundary.py::BoundaryInputs` already accepts `speaker_turn_start_ms` and
  `speaker_turn_end_ms`; unit tests prove both affect fusion. `run_pipeline` never sets them.
- `src/hawedit/pipeline.py::PipelineRun.complete` does not require diarization, so a run can claim
  completeness while Stage 0 is knowingly partial. The text report always prints
  `diarization: not run`, even if a future `IngestResult` contains turns.
- `src/hawedit/reframe.py::OpenCvFaceTracker` chooses a large continuous face. It receives no
  turns or speaker identity, and `render.py` honestly labels its output `FACE_TRACKED`, not
  `SPEAKER_TRACKED`.

## Failure and trust boundaries

- Base ingest artifacts (audio, proxy, duration, VAD, cuts) remain useful if an enabled diarizer
  is operationally unavailable. A diarizer failure must therefore be a separate structured skip,
  not destruction of the base Stage 0 result and not a raw CLI traceback.
- An injected producer is least-trusted model output. Its segments must be type-checked,
  exclusive, within the media clock, non-negative, and deterministically ordered before they
  enter the immutable run record.
- A turn contributes an in-point only when it contains the first selected anchor, and an
  out-point only when it contains the last selected anchor. A gap or unrelated turn supplies no
  boundary. Existing uncaptioned-speech protection remains the final refusal after fusion.
- This slice must not add `pyannote.audio`, download gated weights, change registry integrity, or
  claim active-speaker face association. Those require authenticated bytes, licence attribution,
  target locks, and real labelled multi-speaker footage.

## Chosen seam

1. Introduce a small `Diarizer` protocol and `DiarizationUnavailable` domain error in
   `ingest.py`.
2. Add a pure `attach_diarization` function that validates and returns a replaced
   `IngestResult`; base `ingest` remains responsible only for its existing deterministic media
   artifacts.
3. Add a `diarization` stage field to `PipelineRun`, with explicit skipped/success reporting and
   completeness requiring a measured diarization result.
4. Add a pure turn-selection helper in `diarization.py` and wire its values into
   `BoundaryInputs`.
5. Test through every affected caller: direct validation/round-trip, pipeline success/failure,
   boundary fusion, completion, JSON, and text reporting.

