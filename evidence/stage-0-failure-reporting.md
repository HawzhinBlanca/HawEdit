# Stage 0 failed before a run report existed

Date: 2026-08-09

Decision: D-202

Scope: `src/hawedit/pipeline.py`, `tests/test_pipeline.py`

## Reproduction

`run_pipeline` constructed `PipelineRun` only after `ingest(...)` returned. Injecting either
`IngestError("ffmpeg could not open the media")` or `PermissionError("media read denied")` at that
boundary raised directly. Through `main(..., "--json")`, the outer exception handler printed a
diagnostic to stderr, returned exit 2, and left stdout empty. A machine expecting a run report could
not distinguish an operational Stage 0 outage from malformed arguments or invalid JSON.

That contradicted the module's opening contract: every stage produces either a result or a
`StageSkipped`, and incomplete work exits non-zero without becoming silent.

## Fix

The ingest boundary catches exactly the two expected operational families:

- `IngestError`, the Stage 0 domain refusal;
- `OSError`, covering process launch, filesystem and media-read failures.

It returns a `PipelineRun` with nine explicit skips in pipeline order. `ingest` preserves the
bounded exception type/detail; transcript, index, visual index, discovery, editorial, boundary,
render and delivery each name `Stage 0 ingest` as their dependency. No downstream work is called.

Missing source, invalid identifiers, transcript/schema errors and `AssertionError` remain on the
exception/exit-2 path. The control test injects an assertion at the same seam and requires it to
escape unchanged.

## Executable evidence

Focused verification on the changed tree:

```text
pytest tests/test_pipeline.py     111 passed
ruff check                        passed
ruff format --check               2 files already formatted
mypy --no-incremental             no issues in pipeline.py
git diff --check                  clean
```

The CLI regression requires exit 1, empty stderr, parseable JSON, an ingest skip, and a delivery
skip with the same root blocker. The direct API regression requires all nine skip names and the
programmer-error control.
