# M3.6 — §2's delivery set: the two formats that did not exist

`src/hawedit/delivery.py` · `tests/test_delivery.py` (25 tests) · `tests/test_pipeline.py` ·
D-042

## What was missing

§2's architecture diagram ends with what leaves the system:

> MP4 · SRT/ASS · editing JSON · EDL

MP4 is `render.py`, ASS is `captions.py`, and the editing JSON is §5's clip contract. **SRT and
EDL had never been built** — two of the four things §2 says this system delivers did not exist,
and nothing in the run report said so.

## What the runner now writes

```
clip: 0 .. 4162 ms
render: 4162 ms measured / 4162 requested

=== SRT ===
1
00:00:00,100 --> 00:00:01,700
ڕۆژنامەوانی کوردی.

2
00:00:02,000 --> 00:00:04,100
لە هەولێر.

=== EDL ===
TITLE: fixture fixture-0
FCM: NON-DROP FRAME

001  AX       V     C        00:00:00:00 00:00:04:04 00:00:00:00 00:00:04:04
002  AX       A     C        00:00:00:00 00:00:04:04 00:00:00:00 00:00:04:04
```

## The two timelines

They are opposites, and getting it backwards produces a well-formed, wrong file:

- **The SRT ships beside the MP4**, so its timeline is the clip's — t=0 is the first frame of
  the delivered file. This is exactly the trap M3.5 found in the ASS path. Both subtitle
  formats now take the same `clip_in_ms` and refuse the same out-of-window sentence.
- **The EDL says where the clip came from**, so its *source* timecodes are the source's and
  only its *record* timecodes start at zero. An EDL in clip time tells an editor to conform
  footage from the top of the episode, and nothing about the file looks wrong.

This fixture cannot show the difference — the clip is the whole 4162 ms file, so both ranges
coincide. `test_the_edl_names_the_source_range_and_the_record_range` is the one that does: a
clip at 84 600 ms yields `00:01:24:15 00:01:26:05 00:00:00:00 00:00:01:15`.

## The refusals

- **A period instead of a comma** in an SRT timestamp is WebVTT. A player expecting SRT
  rejects or mis-parses the cue and the subtitles simply do not appear.
- **A non-integer frame rate is refused, not rounded.** 29.97 needs SMPTE drop-frame timecode.
  Non-drop at that rate drifts about 3.6 s per hour against the footage, and the EDL looks
  correct for the whole conform. `frame_rate()` reports the exact ratio ffprobe gives
  (`30000/1001`) rather than a rounded one, so the refusal can happen at all.
- **An empty SRT and a video-only EDL are refused.** Both are valid files that deliver nothing
  — an empty subtitle track, or a conform that drops the Kurdish speech the clip exists for.
- **A clip shorter than one frame** would be a well-formed EDL event that cuts nothing.

An NTSC source therefore produces a correct MP4 and a named `StageSkipped` for delivery, and
`PipelineRun.complete` goes false. Drop-frame timecode is unimplemented, and that is stated
rather than approximated.
