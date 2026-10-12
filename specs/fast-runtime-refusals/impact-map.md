# Fast Refusal Impact Map

Actual Serena evidence and digest are in research.md.

| Changed Symbol | Actual Callers | Regression Scope |
| --- | --- | --- |
| render.encoder_available | render/render_clip; tests/test_render availability, missing-encoder and deterministic-render cases | Existing real encode comparison, available software encoder, explicit unavailable request, repeat renders; new missing executable refusal |
| ingest.ingest | pipeline.pipeline/run_pipeline; tests/test_ingest artifact/source-drift/diarization/ceiling/missing-ffmpeg cases; tests/test_soak invalid-media cases | Existing valid decoded ingest plus real empty/corrupt/truncated inputs; new empty-input precedence/work absence |

_source_digest and _ffmpeg definitions/callers were also mapped. They remain
unchanged. New tests do not replace the current real-media/timeout assertions.
No new dependency or public signature is introduced.
