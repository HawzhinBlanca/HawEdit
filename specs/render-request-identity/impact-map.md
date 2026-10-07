# Actual Caller Impact

Baseline bb24ec67f67a1079d26c524ce72856e792fb9ab9. Actual Serena LSP SDK
FindSymbolTool/FindReferencingSymbolsTool completed 2026-10-07 09:36:53 UTC;
seven definition/reference pairs; every inspected file unchanged throughout.
Immutable raw result: C:/Users/Wareen/AppData/Local/HawEditEvidence/
render-identity-map-20261007/serena-map.json. LSP file-level fallback warnings
remain in its log; these are not invented function signatures.

- `pipeline.run_pipeline`: shared `_build_and_run`, legacy JobManager runner,
  scripts/run_bremer_story_demonstration.py, scripts/run_tier3_demonstration.py;
  direct tests span pipeline, framing parity, ASR admission/stop, checkpoints,
  episodes, events, ingest cache, review cache/findings, condenser/pacing/cost,
  editorial modes and recovery. Signature unchanged; adoption only occurs once
  an actual judged clip reaches the native single-candidate render branch.
- `clip.Provenance`, `to_dict`, `from_dict`: construction/reading in pipeline,
  render, delivery, boundary/caption revisions, candidate review/publication,
  timeline and corresponding tests. Add optional strict field; omit when absent
  to preserve legacy round trips. Signed packets already bind editing JSON.
- `review_candidate_cache.inspect_existing_review_candidate`: only production
  caller is run_pipeline. Check expected/stored request bindings before reusing;
  all prior physical remeasurement/private snapshot guards remain intact.
- `wsl_setup.package_digest`: reused unchanged to bind current package and model
  metadata. Existing WSL/studio/signed evidence consumers unchanged.
- `captions.find_ffmpeg`: reused unchanged to resolve actual tool bytes. Existing
  media/caption/render/upload consumers unchanged.

The new identity helper has no prior callers. It accepts only bounded structured
data, typed dataclass values and regular file/directory snapshots; it is not an
authorization callback or producer. Caller coverage includes actual native render,
cache/refusal, legacy contract, review/publication, revision, pipeline/checkpoint,
episode and web suites via the full canonical gate.

Additional actual Serena storage map completed 09:43:21 UTC with unchanged
ingest_cache.py: `_open`, `_Opened.digest`, `_Opened.check`. Existing callers
are only that module and tests/test_ingest_cache.py. Reuse unchanged `_open` for
separate native path/handle baselines and bounded, deadline-controlled streaming;
do not duplicate or relax the existing Windows mutation guards. Raw result:
render-identity-storage-map-20261007/serena-map.json.
