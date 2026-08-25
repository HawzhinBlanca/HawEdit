# Specification — visual-short-window-provenance

## AC-1 — no raw short-window crash

WHEN a supported visual plan contains a scene whose requested sampling emits one real frame, THE
system SHALL either represent that scene through a declared, checkpoint-compatible policy or
record a bounded, named per-scene refusal, and SHALL NOT expose a raw processor exception.

Evidence: `test_video_input.py`, `test_visual_pipeline.py`, `test_video_reader.py`.

## AC-2 — scene semantics

WHEN HawEdit represents a short scene, THE representation SHALL use no pixels outside the
scene's `[in_ms, out_ms]`, SHALL NOT merge across a shot cut, and SHALL retain the original scene
window as the retrieval/candidate identity.

Evidence: frame extraction regression over a cut-sensitive fixture and representation metadata
assertions.

## AC-3 — explicit provenance

WHEN delivered pixels or their effective clock differ from the requested regular sampling, THE
system SHALL record the representation kind, real source-frame count, delivered-frame count, and
effective sampling rate, SHALL include them in cache identity, and SHALL reject inconsistent
deserialisation.

Evidence: `test_video_input.py`, `test_visual_pipeline.py`.

## AC-4 — exact model hand-off

WHEN the short scene reaches Qwen embedding, Qwen reranking, VideoChat3, or TimeLens, THE system
SHALL prove from the returned processor batch that the delivered representation reached the model
without additional hidden dropping or padding.

Evidence: `test_qwen_visual.py`, `test_video_reader.py`, `test_video_grounding.py`, plus a
processor-only checkpoint measurement.

## AC-5 — bounded timestamps

WHEN a short-scene prompt is generated, THE system SHALL place every model-visible timestamp
inside the original scene duration and SHALL evaluate timestamp floors against the effective
recorded clock rather than an untrue requested rate.

Evidence: `test_video_input.py` and real checkpoint prompt output.

## AC-6 — composed 1-fps operation

WHEN the representative long-form source runs with `--visual-fps 1.0` and the measured 8-frame
hardware ceiling, THE composed pipeline SHALL index every representable planned window, retrieve
at most 50, rerank, expose only 5–10 survivors to VideoChat3 when enough results exist, account for
every unrepresentable window explicitly, and SHALL not abort because a scene is short.

Evidence: `test_visual_pipeline.py`, `test_pipeline.py`, and a real accepted-revision GPU run.

## AC-7 — no regression of ordinary video

WHEN a window already yields at least one complete temporal patch of distinct real frames, THE
system SHALL retain the current extraction, trimming, timestamp, cache, and exact-arrival behavior.

Evidence: the existing video input, visual pipeline, Qwen, VideoChat3, and TimeLens suites.
