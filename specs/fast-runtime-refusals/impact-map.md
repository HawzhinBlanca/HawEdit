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
