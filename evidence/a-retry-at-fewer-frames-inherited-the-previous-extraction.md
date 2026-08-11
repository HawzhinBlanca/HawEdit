# The documented recovery from an OOM failed on the first window every time

Found by running the real 38-minute file, not by reading the code — the same way D-104 was.

## What happened

`BLOCKED.md` #17 / D-108 record that this 3090 Ti reads at most **8 frames per window**, that the
demand is quadratic, and that `--visual-max-frames` exists so a run can be retried lower. That is
the prescribed recovery, and it is the one thing that did not work.

Run 1, at §3's default 64 frames per window, OOMed in the reader — `Tried to allocate 98.56 GiB`,
which is D-106's measured behaviour and not a defect. Run 2, the retry at `max_frames=8` into the
same work directory:

```
hawedit.video_input.FrameCountMismatch: ZAR38MinTest:s0:w0 planned 8 frames and ffmpeg produced
16. More frames than the plan means the ceiling §3 Stage 2 sets is not the ceiling being enforced.
```

ffmpeg had produced 8. The directory held 16:

```
$ ls HawEdit_RealRun/visual/frames/ZAR38MinTest_s0_w0/
000_0001.jpg ... 000_0016.jpg          (16 files)
```

## Why

`extract_window_frames` writes into `dest_dir` with `-y` and then grades the extraction by
globbing the directory:

```python
extracted = tuple(sorted(dest_dir.glob(f"{window.window_index:03d}_*.jpg")))
```

ffmpeg overwrites `000_0001`..`000_000N` and leaves **anything above N** where it is. So a retry
with a *smaller* plan inherits the previous run's tail, and the count that is supposed to grade
what ffmpeg just produced reads 8 fresh frames plus 8 leftovers. The guard then blames the ceiling
— for files ffmpeg did not write.

This is the second half of D-104. That entry fixed this same count being taken over the *parity
step's* output; the count was also being taken over *the previous run's* output, and only a retry
at a lower frame budget exposes it.

## The fix

Clear this window's frames before extracting, so the count grades one extraction:

```python
for stale in dest_dir.glob(f"{window.window_index:03d}_*.jpg"):
    stale.unlink()
```

Scoped by `window_index`, matching the glob it repairs — `_FrameCache` gives each window its own
directory, but this function takes `dest_dir` from its caller.

**The guard is not weakened.** `test_more_frames_than_planned_is_refused` drives a fake ffmpeg
that writes 37 files for a 36-frame plan into a clean directory, and still raises. What changed is
what the count is allowed to see, not what it refuses.

## Proof on the artifact

Re-run against **the same directory that raised**, deliberately not cleared first:

```
before: frames/ZAR38MinTest_s0_w0/  16 files   -> FrameCountMismatch
after : frames/ZAR38MinTest_s0_w0/   8 files   -> run proceeds past w0
```

## Mutation audit — 2/2 lint-clean

```
baseline: GREEN  (42 passed)
baseline lint: clean

CAUGHT   the clearing is removed, so a retry inherits the previous run's tail
          -> test_a_retry_with_a_smaller_plan_does_not_inherit_the_previous_extraction
CAUGHT   the clearing empties the whole directory instead of this window's frames
          -> test_clearing_is_scoped_to_the_window_being_extracted

file restored byte-identical: True
2/2 caught lint-clean
suite after restore: GREEN
```

The second is the control on the first: the lazy fix — emptying `dest_dir` — passes every other
test in the file and silently discards a neighbouring window's extraction.
