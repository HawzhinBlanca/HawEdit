# Impact map — human acceptance kits

| Surface | Existing authority | Callers/consumers | Required regression scope |
|---|---|---|---|
| Sorani corpus | `Corpus`, `CorpusItem`, `Provenance`, corpus importers | `hawedit-asr-bench`, model-promotion evidence | corpus, import, bench, new kit tests |
| Editorial | `EditorialRegressionSet`, `JudgeVerdict`, `repurposing` metrics | editor labelling flow, threshold promotion | editorial, judge, repurposing, new kit tests |
| Diarization | `Segment`, DER, boundary reconciliation | ingest, boundary fusion, speaker tracker, render | diarization, ingest, reframe, render, new kit tests |
| Vertex | governance, `VertexGeminiJudge`, smoke and pipeline CLIs | Path A and Stage 4 client runs | gemini, smoke, pipeline, new kit tests |
| Decisions | `BLUEPRINT.md`, `BLOCKED.md`, `DECISIONS.md` | implementation owners and acceptance report | claims/ledger plus packet snapshot tests |
| Release | release builder and hosted workflows | protected main, tag, GitHub Release | release/workflow/environment plus packet tests |

Task 2 symbol/caller map:

| Symbol | Current callers | Task 2 treatment |
|---|---|---|
| `EditorialRegressionSet.load/evaluate` | `editorial_bench.main`, `tests/test_editorial_bench.py` | Unchanged; the new kit may emit a compatible final set but does not redefine its 20-item floor. |
| `JudgeVerdict.from_dict/to_dict` | provider adapters, pipeline persistence, editorial tests | Reused for strict incumbent/shadow inventory validation; no symbol change. |
| `decide_judge` | editorial regression evaluation and judge tests | Called independently for training and holdout summaries; never with combined labels. |
| `recall_at_k_by_path`, `path_unique_wins`, `temporal_iou`, `misleading_edit_rate`, `sentence_completeness_rate`, `cost_per_source_hour`, `wallclock_per_source_hour` | metric tests and future acceptance reports | Reused by the new final report; existing call behavior remains unchanged. |
| New `editorial_acceptance` coordinator | human study operator only | Owns strict input parsing, byte binding, deterministic sampling/blinding/split, signatures, adjudication, and atomic reports. |

The first bounded implementation shall add a companion Sorani acceptance manifest/verifier rather
than broadening `CorpusItem`. This avoids changing every benchmark fixture and keeps the canonical
raw transcript schema stable. It will call `Corpus.load`, `Corpus.assert_section_8_1_coverage`, and
the existing benchmark CLI contract; callers of those symbols remain behaviorally unchanged.

Any new installed CLI later affects `pyproject.toml`, wheel-member validation, release-workflow
help smoke, README command documentation, and their tests. That change must be taken as its own
explicitly claimed unit. No workflow or release surface is changed by the first library-only unit.
