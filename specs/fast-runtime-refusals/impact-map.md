# Fast Refusal Impact Map

Actual Serena evidence and digest are in research.md.

| Changed Symbol | Actual Callers | Regression Scope |
| --- | --- | --- |
| render.encoder_available | render/render_clip; tests/test_render availability, missing-encoder and deterministic-render cases | Existing real encode comparison, available software encoder, explicit unavailable request, repeat renders; new missing executable refusal |
| ingest.ingest | pipeline.pipeline/run_pipeline; tests/test_ingest artifact/source-drift/diarization/ceiling/missing-ffmpeg cases; tests/test_soak invalid-media cases | Existing valid decoded ingest plus real empty/corrupt/truncated inputs; new empty-input precedence/work absence |

_source_digest and _ffmpeg definitions/callers were also mapped. They remain
unchanged. New tests do not replace the current real-media/timeout assertions.
No new dependency or public signature is introduced.

The follow-up current two-pair actual Serena map is recorded in research.md.
No source/test caller invokes encoder_available.cache_clear/cache_info; removing
that internal decorator does not remove a consumed public API. Add a real
missing-then-copied executable regression and physical ordinary/extended ftyp
refusals. Preserve all valid-container, source-drift, actual NVENC and timing
tests. Probe timing stays30seconds; no cached answer is runtime admission.
# 2026-10-13 Ingest Runner Continuation

Actual current Serena three-pair map at clean dd172d5, SHA256
1f5c2ab8edf1fa6990e553ce8a8a4f3d904cc1c4d328f47a24be4ef2997207a7.
`_run` has exactly two actual production callers: `probe_stream` and
`_extract_once`. No signature or successful-result shape changes.

`probe_stream` consumers include probe_duration_ms, IngestCache.load,
pipeline.proxy_dimensions, render.frame_rate, diarization_acceptance._video_identity,
editorial_acceptance._verified_video_identity, vertex_acceptance._default_media_probe,
and the historical Bremer/tier3 demonstration scripts. Duration/revision/export
tests additionally exercise this shared probe. `_extract_once` serves
extract_audio/extract_proxy and then ingest/pipeline/cache. Existing atomic-cache
and timing regressions remain required. New tests call the actual runner and
extraction path; no replacement runner is introduced.

Required whole cohorts: ingest, ingest_cache, fast_runtime_refusals,
ingest_runtime_refusals, pipeline, render and render boundary/caption revision,
diarization/editorial/vertex acceptance, then the exact full gate covering all
remaining transitive callers. Historical demonstration scripts are typechecked;
they are not executed as autonomous quality evidence.
