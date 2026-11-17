# Diarizer Wire Impact Map

Fresh actual Serena map at clean029f9c:five definitions found once, raw records retained
in diarizer-wire-before-map.json. No signature is inferred from an old stub or invented.

| Symbol | References | Real affected callers / required verification |
|---|---|---|
| PyannoteDiarizer | 11 | create_diarizer construction/type/export; pipeline tests test_the_diarize_flag_reaches_run_pipeline_as_a_producer and test_an_unavailable_diarizer_never_claims_speaker_tracking; existing adapter import/missing weights/revision/extra tests |
| PyannoteDiarizer.diarize | 2 concrete | Existing missing-weights and missing-extra tests; dynamic Diarizer protocol calls through attach_diarization are also affected, not excluded by this concrete count |
| convert_annotation_to_segments | 6 | Actual adapter, import/export and three timing/zero-length/overlap tests. Public direct Annotation contract unchanged |
| create_diarizer | 3 | Shared pipeline._build_and_run import/call and export; new tests invoke the real factory, model path/device values preserved |
| attach_diarization | 9 | Shared run_pipeline invocation, imports/export and ingest/adapter tests; new wrapped producer integration retains exclusive/media-clock refusal |

Only adapter method output selection changes. Ingest, converter, factory, canonical ASR,
pipeline builder, model/revision/device policy and existing tests are not rewritten.
Complete tests/test_pyannote_adapter.py, test_pyannote_wire.py, test_ingest.py and
test_pipeline.py plus the exact gate cover the affected test/caller families. New test-side
upstream doubles are explicitly wire controls, never model-quality or weight-loader proof.
No tests/fixtures/golden/harness/policy change or parallel checkout writer.
