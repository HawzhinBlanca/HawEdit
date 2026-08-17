# Adversarial pass #8 — the shipped clip, and the guard nobody drove

> Run 2026-08-09 on hawapc01 against `1ee009c`.
> Target: **M3.4**, DONE — §8.3's boundary invariant on every shipped clip.

M3.4 is the row whose history is the sharpest in this repo: the invariant "had been asserted on the
`Clip` object; `RenderResult.duration_ms` was the request echoed back and the file was never opened",
and fixing it found that *every* `run_pipeline` render had been silently truncated. So it is the row
most worth attacking again.

## Part 1 — render for real, and measure the file independently

The repo's own `probe_duration_ms` cannot be used to check itself, so ffprobe was called directly:

```
render stage: RenderResult
  file            : fixture-s0-1.mp4, 101,332 bytes
  requested_ms    : 4162
  measured_ms     : 4162   (the repo's own probe)
  ffprobe direct  : 4162   (this script, independent)
  clip final span : 0..4162 ms

the two probes agree            : True
file is not short of the request: True
```

Note the trap in that agreement: `measured == requested` exactly, so **this path alone cannot tell a
probe from an echo**. That is what part 2 is for.

## Part 2 — revert each mechanism

```
baseline FAILED=0
RED    the measured duration is the request echoed back (the original defect)   (1 test)
RED    the shipped-clip guard never fires                                       (2 tests)
RED    the tolerance widens to ten frames                                       (1 test)
RED    the file is never opened at all                                          (1 test)
GREEN  one frame is assumed to be 40 ms for every source          <- UNPROTECTED
GREEN  the guard compares the request against itself              <- UNPROTECTED
```

**The guard's wiring.** `assert_encoded_span(duration_ms, duration_ms, …)` — comparing the request
against itself — left the suite green. The function is unit-tested with real numbers, but it is reached
only through `render_clip`, and truncation by a short source is prevented upstream, so no test ever
drove it. Third appearance of this shape: D-137 and D-143 were both "the function is tested, the trip
to it is not".

**The frame rate.** `frame_duration_ms` → `return 40` survived, against its own docstring: *"Not a
constant … a 30 fps source is 33 ms … 'too loose' is the direction that ships a truncated clip."* Every
fixture is 25 fps, where 40 is correct — D-086/D-088/D-101's blindness again.

## The fix

A test that drives `render_clip` into a short measurement and expects the refusal, with a control that
an exact measurement still renders. The *output's* measurement is replaced rather than the encode,
because the arithmetic is already covered; the gap was proof that `render_clip` passes the measured
value in.

**A first attempt was wrong and the error was useful.** Patching `probe_duration_ms` wholesale tripped
the **pre-flight** refusal instead — *"clip m2-4 ends at 2700 ms but kurdish-speech-3cuts.mp4 is 2000
ms"* — because that check probes the source with the same helper. It fired, which is evidence that
guard is wired and tested. The patch is now keyed to the output file's name.

For the rate, a 30 fps source is generated so the constant and the measurement differ: **33 ms against
40**, with the 25 fps fixture asserted at 40 in the same test.

```
baseline FAILED=0
RED  the measured duration is the request echoed back
RED  the shipped-clip guard never fires
RED  the tolerance widens to ten frames
RED  the file is never opened at all
RED  one frame is assumed to be 40 ms for every source     <- test_one_frame_is_read_from_the_source…
RED  the guard compares the request against itself         <- test_render_refuses_when_the_written…

6/6
```

Gate: `VERIFY OK — 1231 passed, 0 skipped`.
