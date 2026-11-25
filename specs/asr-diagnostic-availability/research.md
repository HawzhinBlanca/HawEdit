# ASR Diagnostic Availability

Research source: fd1468a2b405ff0ecc43755eea9c1b72a3ad4e23, 2026-10-05.

The full ZAR38 retest refused incomplete decoding at 905634..917022 ms. No
raw transcript or reel was produced, but PipelineRun.to_dict emitted zero
missing-speech duration and empty correction/routing measurements. These are
unknown, not measured zeros. This is separate from the unresolved decoding
failure; it cannot improve transcription or certify native fidelity.

Actual Serena definitions/references were captured before edits in
C:/Users/Wareen/AppData/Local/HawEditEvidence/asr-diagnostics-fd1468a-20261005/serena-reporting-map.json.
PipelineRun: 117 reference occurrences; to_dict: 33; run_pipeline: 202.
Import-containing-symbol fallbacks are file anchors, not invented caller counts.

run_pipeline obtains diagnostics after TranscriptStore.verify_raw_integrity,
before rejecting known damaged raw transcripts. Preserve those failure records
and the existing genuine-zero control. durable_workflow persists the JSON-safe
dictionary without interpreting these numeric fields. Supplemental rg found no
frontend numeric consumer. Human report prints routing only when records exist.

Grounding: BLUEPRINT sections 3, 5 and 8.1; D-145 reporting and D-281 admission.
Vault incident: HawEdit - Canonical Completion Admission Repair 2026-10-05.

No model, decoding, canonical transcript schema, billing or publication change.
