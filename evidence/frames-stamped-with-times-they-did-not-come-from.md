# Frames stamped with times they did not come from

> Measured 2026-08-10 on hawapc01 against `e5a3f22`, ffmpeg 8.1.1-full, on
> `tests/fixtures/kurdish-speech-3cuts.mp4` — **4,162 ms**, three static shots.

`extract_judge_frames` samples up to 20 JPEGs from a candidate span and hands them to §3 Stage 4 as
the pixels the verdict is formed on. Two things were wrong with it.

## 1. The stamps were derived from the wrong number

```python
step_ms = (out_ms - in_ms) / len(paths)      # frames that came back
```

ffmpeg is told `fps = count / duration_s`, so frame *i* comes from
`in_ms + (i + 0.5) × (span / count)`. The two agree only while ffmpeg returns exactly `count`
frames. Ask for a span the source cannot fill and it returns fewer — and the survivors are spread
across the whole request:

```
span 0..13000 ms, count=20, on a 4162 ms file

before   6 frames   1083, 3250, 5417, 7583, 9750, 11917     4 stamped past the end of the file
         4 distinct images for 6 stamps — two pairs identical

after    6 frames    325,  975, 1625, 2275, 2925,  3575     0 stamped past the end
```

Nothing downstream can see this. A mis-stamped frame is a valid JPEG of real pixels, and
`JudgeRequest.__post_init__` checks only that each timestamp lies inside the *candidate span* —
which a stretched stamp does, by construction. The judge is simply told a shot is from a moment the
video never had.

## 2. `glob` could return an earlier run's frames

Adversarial pass #15 added `if len(paths) > count: raise` for this, with a test. It catches only
leftovers that push the total *over* `count`. ffmpeg overwrites `judge-001.jpg` upward, so a run
producing fewer frames than the last leaves the older, higher-numbered files behind:

```
0..4000   count=20  ->  20 files written
0..13000  count=20  ->   6 written, 14 left over
                         len(paths) == 20, so no refusal
                         the call returned 20 frames, 14 of them the previous span's pixels
```

The pipeline names the Stage 4 directory per candidate, so re-running a candidate reaches it.

**This is also why a number in yesterday's record was wrong.** D-152 measured `0..13000` as
returning "20 frames" — my probe had reused one output directory across three spans, so 14 of those
20 were leftovers from the previous call. The measurement of the defect was corrupted by the defect.
Corrected in D-152, `BLOCKED.md` #20, `README.md` and that evidence file.

## The fix

* `step_ms = (out_ms - in_ms) / count` — the rate ffmpeg was given. Stamps are true by
  construction, so no clamp and no threshold.
* The stale check moves ahead of ffmpeg and fires on **any** pre-existing `judge-*.jpg`, keeping
  pass #15's refusal and closing the case it could not see. `len(paths) > count` stays as the
  second net.

## Proof

```
baseline green: True

RED  the defect restored: stamps derived from the frames returned, not the rate given
RED  the stale-frame guard is removed entirely
RED  the stale guard reverts to firing only when the count is exceeded
RED  each frame is stamped at the start of its bucket instead of its centre
RED  the stamps are clamped to the span end, hiding a stretched sample

5/5
restored and green: True
```

Asserted on the decoded frames — the stamps of the JPEGs that come back, checked against the rate
and against the source's real duration. The control requires a span three times the file's length
to still return **real** frames from the part that exists (`2 <= len(frames) < 20`, every payload a
JPEG), because refusing everything would satisfy "nothing is stamped past the end" while measuring
nothing.

Gate: `VERIFY OK — hawedit gate green`, 1499 tests (floor 1494 → 1499).
