# Impact map — human acceptance kits

| Surface | Existing authority | Callers/consumers | Required regression scope |
|---|---|---|---|
| Sorani corpus | `Corpus`, `CorpusItem`, `Provenance`, corpus importers | `hawedit-asr-bench`, model-promotion evidence | corpus, import, bench, new kit tests |
| Editorial | `EditorialRegressionSet`, `JudgeVerdict`, `repurposing` metrics | editor labelling flow, threshold promotion | editorial, judge, repurposing, new kit tests |
| Diarization | `Segment`, DER, boundary reconciliation | ingest, boundary fusion, speaker tracker, render | diarization, ingest, reframe, render, new kit tests |
| Vertex | governance, `VertexGeminiJudge`, smoke and pipeline CLIs | Path A and Stage 4 client runs | gemini, smoke, pipeline, new kit tests |
| Decisions | `BLUEPRINT.md`, `BLOCKED.md`, `DECISIONS.md` | implementation owners and acceptance report | claims/ledger plus packet snapshot tests |
| Release | release builder and hosted workflows | protected main, tag, GitHub Release | release/workflow/environment plus packet tests |

The first bounded implementation shall add a companion Sorani acceptance manifest/verifier rather
than broadening `CorpusItem`. This avoids changing every benchmark fixture and keeps the canonical
raw transcript schema stable. It will call `Corpus.load`, `Corpus.assert_section_8_1_coverage`, and
the existing benchmark CLI contract; callers of those symbols remain behaviorally unchanged.

Any new installed CLI later affects `pyproject.toml`, wheel-member validation, release-workflow
help smoke, README command documentation, and their tests. That change must be taken as its own
explicitly claimed unit. No workflow or release surface is changed by the first library-only unit.
