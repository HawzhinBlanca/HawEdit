# NTSC footage shipped four fifths of a delivery set, and it looked whole

> Measured 2026-08-09 on hawapc01 against `7fa15b6`, real ffmpeg 8.1.1, real transcode.

§2's delivery set is an MP4, an ASS, an SRT, an editing JSON and an EDL. `run_pipeline` wrote
the JSON, then the SRT, and then *built* the EDL — and the EDL is the one that legitimately
refuses. `build_edl` will not fake SMPTE drop-frame timecode for an NTSC rate, on purpose: at
29.97 fps a non-drop EDL drifts about 3.6 s per hour and looks correct the whole time.

So on ordinary broadcast footage the run left a playable captioned MP4 with an SRT and a JSON
beside it, no EDL, and reported the stage skipped. D-071 named delivery atomicity as an open
shortfall and did not fix it; this is that shortfall, and it is reachable on the commonest
professional frame rate rather than on an exotic edge case.

## Reproduced, on a real 29.97 fps transcode

```
$ ffmpeg -i tests/fixtures/kurdish-speech-3cuts.mp4 -r 30000/1001 -c:v libx264 -c:a aac ntsc.mp4
$ python -c "from hawedit.render import frame_rate; print(frame_rate(Path('ntsc.mp4')))"
29.97002997002997
```

Running the full pipeline over it, before the fix:

```
render  : RenderResult(..., width=1080, height=1920, measured_duration_ms=1902,
                       captions_burned_in=True)
delivery: SKIPPED — blocked_by=('§2 delivery set',)
  reason: 29.97002997002997 fps needs SMPTE drop-frame timecode, which this does not write…
run.complete = False

WHAT IS ON DISK:
  ntsc-s0-0.ass         700 bytes
  ntsc-s0-0.json       1691 bytes
  ntsc-s0-0.mp4       51161 bytes
  ntsc-s0-0.srt          72 bytes
                                     <- no .edl

  ntsc-s0-0.mp4 decodes as: width=1080  height=1920  nb_frames=57  duration=1.901900
```

The MP4 is not a stub or a truncation — it decodes as a complete 1080×1920 vertical clip with
burned-in captions. The run reported itself incomplete, honestly; the *files* did not.

After the fix, same command:

```
WHAT IS ON DISK:
  ntsc-s0-0.ass         700 bytes
  ntsc-s0-0.mp4       51161 bytes
```

## The fix

The failure was interleaving fallible *building* with *writing*. Nothing in the sequence needs a
file to exist before the next step, so all three are built first and written only once every one
of them exists. The `except` also unlinks the three sidecar paths, which covers a write that
fails partway through — disk full, permissions — so the set is all-or-none in both directions.

**The MP4 and the ASS are deliberately kept.** Stage 6 genuinely succeeded and `run.render`
reports that path; deleting its output because a later stage failed would make the report a lie
and would throw away an encode over a sidecar. Rejected on those grounds, not overlooked.

## The control

`test_an_edl_safe_source_still_writes_the_whole_delivery_set` runs the same call against the
25 fps fixture and requires all three sidecars present. A fix that cleaned up unconditionally,
or one that stopped building the set at all, passes the NTSC test and fails this one.

## Mutation audit, against a baseline verified green first

```
baseline: GREEN
CAUGHT   the EDL is built after the first two sidecars are written (the original defect)
CAUGHT   the cleanup on failure is removed
CAUGHT   OSError is no longer caught, so a mid-write failure escapes uncleaned
CAUGHT   cleanup also deletes the render, making run.render.path a lie

4/4
```

**This took two corrections, both worth recording.**

*The audit first reported the original defect as SURVIVED*, and it was right to: the cleanup loop
alone makes the final disk state correct, so reverting the build-before-write ordering changed
nothing any test could see. Two changes had been made and only one was load-bearing. The
ordering is still worth keeping — written-then-deleted leaves a window in which the partial set
exists on disk, and a crash inside it (power loss, SIGKILL) strands exactly what this fixes —
but an untested property is not a property. `test_a_refused_edl_never_writes_a_sidecar_at_all`
records every `Path.write_text` and asserts no sidecar write is *attempted*, which is the only
way to see the difference between "cleaned up" and "never written".

*Then the mutation itself was wrong.* It inserted a second `build_edl` while leaving the early
one in place, so the refusal still fired before any write and the defect was never actually
reintroduced. Rewritten to remove the early build. A mutation that does not restore the bug
measures the test against nothing, which is the same failure as a green baseline nobody checked.

*And the first version of the write-attempt test failed for the wrong reason*: it matched
sidecars by suffix, and Stage 1 writes `transcript.raw.json` under the work directory too. It
compares exact paths now.

## What this does not fix

An NTSC source still produces no EDL. That is correct behaviour — `delivery.py` refuses drop-frame
rather than shipping a conform that drifts — and the run says so. Writing real drop-frame
timecode is a separate piece of work and is not claimed here.

Gate: `VERIFY OK — 1083 passed, 0 skipped`.
