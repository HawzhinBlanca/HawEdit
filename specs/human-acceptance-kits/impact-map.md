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

Task 3 symbol/caller map:

| Symbol | Current callers | Task 3 treatment |
|---|---|---|
| `Diarizer.diarize`, `attach_diarization` | `pipeline.run_pipeline`, ingest and pipeline tests | Unchanged; the kit measures strict exclusive output but does not create a gated production adapter. |
| `diarization_error_rate`, new `overlap_aware_diarization_error_rate` | diarization and acceptance tests | Production/community scoring keeps strict exclusive turns; the separate control scorer handles 3.1 overlap as speaker-time false alarm/confusion without becoming a pipeline route. |
| `boundary_reconciliation` | diarization tests only | Reused against the same signed aligned reference words for each system; its tolerance is reported, not tuned here. |
| `SpeakerSubjectTracker.track_speakers`, `validate_speaker_focus_points` | `pipeline.run_pipeline` and injected seam tests | The kit validates each system's claimed points against its measured exclusive turns, then compares mapped speaker identity and centre positions with human reference points. |
| `OpenCvFaceTracker` | pipeline CLI and reframe tests | Remains the explicit non-speaker fallback; its output is not relabelled as speaker-tracked evidence. |
| Registry Community-1 entry and 3.1 benchmark control | model readiness, licence/claims tests | Read-only trust anchors for exact ids, role and licences; gated acceptance/checkpoint bytes and the control revision remain human/runtime evidence. |
| New `diarization_acceptance` coordinator | human study operator only | Owns strict media/reference/model-run manifests, signatures, content revalidation, per-system DER/boundary/association/crop metrics, fallback reporting and atomic result publication. It does not load gated models. |

Task 4 Vertex symbol/caller map:

| Symbol | Current callers | Task 4 treatment |
|---|---|---|
| `VertexGeminiJudge` | pipeline CLI, Path A, Stage 4 and Gemini tests | Reused as the only model transport. Its regional URL, ADC header, governance, response validation and no-retry policy remain authoritative. |
| `GeminiJudge.judge` | pipeline editorial judge and adapter tests | Delegates to a new counted operation so ordinary behavior is unchanged while acceptance can bind the exact authorising count to one generation. |
| New `GeminiJudge.judge_with_count` | Vertex acceptance coordinator and Gemini tests | Counts once, enforces both §3 and owner-approved ceilings, attempts generation once, and returns the exact count with the validated verdict. |
| `extract_judge_frames` | pipeline Stage 4 and smoke | Reused after all local, signed, ADC and billing checks; no second frame extraction policy is introduced. |
| `NormalizedTranscript` | Path A, indexes and model boundaries | Parsed from the exact private artifact; raw transcripts and non-normalised request text remain refused. |
| New `vertex_acceptance` coordinator | human operator only | Owns private manifest validation, approval signature, ADC/billing preflight, durable one-attempt reservation, redacted evidence and no transport during preparation. |
| `windows_security.create_private_directory`, `assert_private_windows_path` | model-fetch staging and the new Vertex coordinator | Reused without signature changes so confidential frame/evidence workspaces receive a real protected Windows DACL; POSIX uses owner-only mode 0700. |
| New `decision_packets.prepare_decision_packets` | human product owner only | Reads the six exact `BLOCKED.md` sections plus frozen blueprint/evidence bytes and publishes deterministic pages, an unset owner template and a machine-readable manifest. It has no runtime pipeline caller and makes no decision itself. |
| `BLOCKED.md`, `BLUEPRINT.md`, named `evidence/*.md` inputs | claims and human review | Read-only authorities. Their section/file digests are emitted so a packet becomes stale rather than silently carrying old measurements after any source changes. |

The first bounded implementation shall add a companion Sorani acceptance manifest/verifier rather
than broadening `CorpusItem`. This avoids changing every benchmark fixture and keeps the canonical
raw transcript schema stable. It will call `Corpus.load`, `Corpus.assert_section_8_1_coverage`, and
the existing benchmark CLI contract; callers of those symbols remain behaviorally unchanged.

Any new installed CLI later affects `pyproject.toml`, wheel-member validation, release-workflow
help smoke, README command documentation, and their tests. That change must be taken as its own
explicitly claimed unit. No workflow or release surface is changed by the first library-only unit.
