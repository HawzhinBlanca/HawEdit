# Impact map — true-10-10-acceptance

This map records the current production seams and their direct consumers. Before a task edits one
of these symbols, its task-specific research must re-run the corresponding caller search because
the accepted `main` revision may have moved.

| Area | Primary symbols/files | Direct production callers/consumers | Required regression surface |
|---|---|---|---|
| Promotion | `.github/workflows/gate.yml`, `release.yml`, `gpu-readiness.yml` | GitHub branch protection and release events | workflow contract tests, live exact-SHA checks |
| WSL ASR | `WslOmniAsrProducer`, `asr_worker.main`, `wsl_setup`, `wsl_vex_gate` | `pipeline.main`, `ModelStore`, main-only workflow | ASR, worker, setup, models, VEX tests |
| ASR quality | `bench.run_benchmark`, corpus importers | `hawedit-bench`, evidence publisher | corpus/import/bench tests and real corpus manifest |
| Path B | `VisualComposer.discover`, `build_visual_composer` | `run_pipeline` | visual pipeline, Qwen, reader, video-input, pipeline tests |
| Stage 4 | `extract_judge_frames`, `GeminiJudge`, `VertexGeminiJudge` | Path A, editorial judge stage, smoke CLI | keyframe, Gemini, judge, smoke, pipeline tests |
| TimeLens | `TimeLens2Grounder.ground_all/close` | `run_pipeline` boundary stage | grounding, timelens, boundary, pipeline tests |
| Reframe | `OpenCvFaceTracker`, `render_clip` subject tracker seam | `pipeline.main`, Stage 6 | reframe, render, pipeline tests |
| Diarization | `diarization_error_rate`, `IngestResult.diarization` | Stage 0 ingest, Stage 5 boundary inputs, reframe association | diarization, ingest, boundary, reframe tests |
| Editorial benchmark | `EditorialRegressionSet`, `repurposing` metrics | `hawedit-editorial-bench`, promotion decision | editorial/repurposing tests and labelled set |
| Release | `build_reproducible_wheel`, release workflows | `hawedit-release`, GitHub OIDC attester | release/build/workflow/environment tests |
| Final acceptance | `PROGRESS.md`, `BLOCKED.md`, `evidence/` | operators and owner release decision | claims/ledger tests plus signed acceptance matrix |

## Change-coupling constraints

- WSL source changes alter the receipt source digest and therefore require a new runtime receipt,
  current VEX applicability, and new live evidence. Policy digests must never be edited merely to
  make a stale runtime pass.
- Visual window/fps changes alter the retrieval unit and invalidate prior Recall@K comparisons.
- A diarization implementation affects ingest schema, sentence/boundary inputs, reframe identity,
  model provisioning, licence attribution, and benchmark metrics as one unit.
- A Gemini routing change affects governance preflight, credential loading, request accounting,
  smoke behavior, and confidential evidence as one unit.
- Release workflow changes are enforcement-surface edits and require `.codystem-allow-self-edit`,
  exact workflow tests, a canonical gate, and a hosted run before acceptance.
- `BLUEPRINT.md` is frozen. Adding SAM 3/Molmo2, changing the canonical visual unit, or weakening
  confidential routing requires an ADR and the owner decision recorded in `BLOCKED.md`; code alone
  cannot resolve those choices.
