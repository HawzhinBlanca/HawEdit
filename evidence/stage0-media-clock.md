# Stage 0 media-clock containment · 2026-08-09

## Defect reproduced on real media

`tests/fixtures/kurdish-speech-3cuts.mp4` probes at **4162 ms**, but the extracted audio plus
Silero padding produced a final VAD region of **1954..4180 ms**. The real Stage 1 run therefore
had enough valid PCM to align and persist words through 4180 ms even though no video frame exists
after 4162 ms.

This was not an ASR rounding defect. Stage 1 correctly measured the PCM it received. The missing
invariant was at Stage 0, where the audio and video clocks first meet.

## Contract implemented

`ingest()` probes the media duration once, then intersects VAD regions with
`[0, duration_ms]` before applying the 40-second ASR ceiling. Overlapping speech is retained and
clipped only at the media edge; speech wholly outside the video is omitted. Invalid zero- or
negative-length VAD regions and non-positive media durations are refused.

The real fixture now records **1954..4162 ms** and the runner passes that exact bound to its
canonical ASR producer.

## Verification

- 114 focused ingest, ASR, and pipeline tests passed before mutation auditing.
- A runner integration test captures the production ASR call and proves its latest segment end
  equals `IngestResult.duration_ms`.
- Ruff, formatting, and strict mypy passed for the changed files.
- Final canonical gate: **1198 passed, zero skipped**; Ruff, formatting, and strict mypy clean.

Mutation audit, with each exact source edit restored:

1. bypass `_clip_speech_to_media` in `ingest()` — the real regression fails at 4180 != 4162;
2. remove the `min(duration_ms, segment.end_ms)` clamp — the intersection unit test retains
   both an overlong region and a wholly out-of-range region; and
3. remove malformed-span refusal — the corrupt zero-length region disappears silently and the
   refusal test fails.

Result: **3/3 caught**.

## Boundary

This establishes timestamp containment, not Sorani recognition accuracy. The fixture is
synthetic Kurmanji and remains only a real-media execution/VAD control. Labelled Sorani CER and
alignment quality remain external benchmark requirements.
