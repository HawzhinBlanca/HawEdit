# Impact map — integrate the production branch

## Direct conflict surfaces

| File | Affected behavior | Required review |
|---|---|---|
| `src/hawedit/pipeline.py` | `PipelineRun`, `run_pipeline`, CLI construction/reporting, escalation, Stage 6 QC/render/delivery | Compose structurally; run the full pipeline, durable, proposal, agent, render, caption, reframe, and CLI tests |
| `pyproject.toml` | optional dependencies and console scripts | Preserve both script sets and the `agentic` extra; verify clean wheel/entry-point contracts |
| `security/wsl-asr-vex.json` | source-bound VEX applicability | Recompute merged source digest; retain reviewed/expiry facts |
| `scripts/test-count.floor` | canonical pass floor | Start from accepted main; permit only the gate to ratchet |
| `DECISIONS.md` | D-247..D-250 plus D-A decisions | Preserve both ordered histories and unique identifiers |
| `AUDIT_REPORT.md` | release/readiness claims | Preserve both claim sets and eliminate contradictions against merged behavior |

## Auto-merged surfaces requiring semantic review

- `PROGRESS.md`, `README.md`, `tests/test_claims.py`
- `src/hawedit/judge.py`, `tests/test_judge.py`
- `tests/test_pipeline.py`

## Callers and downstream contracts

- `run_pipeline` is called throughout `tests/test_pipeline.py`, revision/proposal flows, the durable
  workflow, and the command-line runner.
- `build_ass` is consumed by pipeline, delivery, render and caption-timing tests.
- `render_clip` is consumed by pipeline, proposal equivalence and artifact-inspection paths.
- `OpenCvFaceTracker` is constructed by the CLI and validated through reframe and pipeline tests.
- `Qc` construction and `dead_air_flags` affect renderability, quality checks, developer reports,
  durable runs and final delivery.
- `[project.scripts]` is consumed by release-wheel validation and installed-wheel smoke tests.

No caller is exempted. The full canonical gate is the final impact check after focused conflict tests.
