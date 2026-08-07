# M3.4 — §8.3's third bullet: the invariant on the *shipped* clip, not the plan

`src/hawedit/render.py` · `src/hawedit/boundary.py` · `src/hawedit/pipeline.py` ·
`tests/test_render.py` · `tests/test_boundary.py` · D-040

## What §8.3 asks for

> ### 8.3 Render regression tests
> - Golden-file Kurdish caption render, compared per build ✅ M3.2
> - Font coverage assertion across the full Kurdish character set ✅ M3.1
> - **Boundary invariant: assert `final_in <= anchor_in` and `final_out >= anchor_out` on
>   every shipped clip**

The third was read as "on every clip object". `render_clip` called `assert_renderable()`,
checked the numbers, invoked ffmpeg, and returned `duration_ms` — *the requested duration,
echoed back*. The file it had just written was never opened.

## Measured

```
requested duration : 8000 ms
file on disk       : 4180 ms
source is          : 4162 ms
encode exit        : 0
```

ffmpeg cuts what exists and stops. It exits 0. The result object then reports 8000 ms about a
4180 ms file, and the shipped clip ends 3.8 s before its own `final_out` — mid-sentence, the
one thing Kurdish invariant #2 exists to prevent — with every check on the numbers green.

## The upstream cause, found by the new check

The first thing the check caught was this project's own end-to-end fixture:

```
media                          : 4162 ms
anchor_out                     : 4100 ms
final_out, duration unknown    : 4300 ms  -> 138 ms past the file
final_out, duration supplied   : 4162 ms  (extended by tail)
invariant #2 holds either way  : True True
```

§3 Stage 5's out-point set always includes `anchor_out + 200 ms tail`. On a short source that
alone runs past the end of the file. `fuse_boundary` already clamps `final_in` at 0 — "a clip
cannot start before the media does" — and had no matching upper clamp, because nothing told it
where the media stopped. So `run_pipeline` had been rendering a clip 138 ms shorter than the
boundary it recorded, on every run, and the suite was green.

`BoundaryInputs.media_duration_ms` closes it, and the pipeline passes the duration Stage 0
already probed. An anchor past the end is **refused rather than clamped**: clamping the tail is
safe for invariant #2 because the anchor still fits, but clamping an anchor that does not fit
would produce `final_out < anchor_out` — the invariant violated by its own fix.

## What now runs

1. **Before the encode** — `clip.out_ms` is checked against the probed source duration. Cheap,
   deterministic, and it names both numbers.
2. **After the encode** — the file is probed and compared to the request, with one frame of
   slack taken from the file's own rate rather than assumed. Measured on the real fixture:
   correct cuts came back exact except one, which was `+40 ms`, exactly one frame at 25 fps.
   Only the short side is a defect.
3. **`RenderResult` carries both numbers** — `requested_duration_ms` and
   `measured_duration_ms`. They agreed silently for as long as nobody looked.

## Already honest

`evidence/m2-4-rendered-clip.mp4`, the committed M2.4 deliverable, measures **2240 ms** against
a 2200 ms request — one frame of container rounding, well inside the 4162 ms source. That
artifact was never truncated, and its evidence file already said the duration was probed off
the encoded file. It was the code path, not that clip, that was taking the request on trust.
