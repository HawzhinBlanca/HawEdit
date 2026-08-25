# Impact map — media/transcript byte identity

| Changed surface | Affected callers/tests |
|---|---|
| `IngestResult` schema and `ingest()` | `attach_diarization`, pipeline reports, `tests/test_ingest.py`, the one direct pipeline fixture constructor |
| `RawTranscript` schema | ASR/worker serialization, transcript store, pipeline helper transcripts, transcript schema tests |
| Stage 1 reuse key | `run_pipeline` canonical ASR cache tests and immutable-store collision tests |
| Source-drift guards | Visual composer, Stage 4 keyframes, TimeLens, speaker/face tracking, render/delivery integration tests |
| `Clip` schema/render gate | `pipeline` clip construction, `tests/test_clip.py`, `tests/test_render.py`, audit regression helper |
| Shipped editing JSON | full real-media pipeline fixture and delivery-set assertions |

Tests must cover each source reader rather than merely checking helper spelling. The primary
adversaries are same-id/different-bytes supplied media, a mutation during visual extraction, a
mutation during render, an unbound legacy raw transcript, and an unbound legacy clip.
