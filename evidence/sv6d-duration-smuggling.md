# The 9999s claim rode back in on a duration phrase, on every window this pipeline plans

> Measured 2026-08-09 on hawapc01 against `7c017eb`, against a green 1,137 baseline.

M5.3's row headlines a real defect and its fix: `speaker gestures at 9999s` — 2.78 hours — once
"constructed cleanly for a 12-second window", and `assert_sv6d_within_window` "closes it".

It closed the bare case. It did not close the case with a duration attached.

## The rule, and why it is not simply wrong

The guard requires **some** cited time inside the window, not all of them. Its own docstring
explains why: *"A label may legitimately mention a length as well as a moment — 'slow push-in over
3s, starting 5:04' cites 3 000 ms and 304 000 ms, and only the second is a point on the timeline.
Requiring all of them would reject honest labels; requiring none is what let 9999s through."*

That tradeoff is sound. The problem is that a duration is a small number, and on a window starting
near zero *any* small number is inside the window.

## Measured on the windows Stage 0 actually plans

```
label: speaker gestures at 9999s, held over 1s
cited ms: (9999000, 1000)

  window 0..1400    'over 1s' -> ACCEPTED (9999s claim survives)
  window 1400..2800 'over 2s' -> ACCEPTED
  window 2800..4162 'over 3s' -> ACCEPTED

the window the cited tests use:
  300000..312000              -> refused
```

Those three windows are what `plan_scene_windows` produces for the only media in this checkout. The
cited tests used 300000..312000 — the one distance from zero where 1000 ms falls outside — so the
rule bit exactly where it was tested and nowhere the pipeline runs. Same shape as D-095 one
iteration earlier: a test that was correct and blind because its fixture happened to satisfy it.

## The fix, and why it needed no threshold

The discriminator is already in the arguments. In the legitimate case the out-of-window number is a
small **duration** and the in-window one is the **moment**; in the defect it is reversed, with the
out-of-window number vastly larger than the scene. So:

> a cited time outside the window is admissible only if it is shorter than the window itself —
> the longest duration anything inside it can have.

Derived from `in_ms` and `out_ms`, not chosen. That is what makes this a fix rather than a third
`BLOCKED` entry alongside #14 and #15, both of which are genuinely unset thresholds.

Verified in all four directions before a test was written:

```
the exploit, on every window Stage 0 plans:
  0..1400    -> refused
  1400..2800 -> refused
  2800..4162 -> refused

the docstring's legitimate label (must stay ACCEPTED):
  300000..312000 'slow push-in over 3s, starting 5:04' -> ACCEPTED

the original headline defect (9999s alone on a 12s window):
  300000..312000 -> refused

an ordinary honest label:
  0..1400 'a red number 0 centred, 0.4s' -> ACCEPTED
```

## Mutation audit, against a baseline verified green first

```
baseline FAILED=0
CAUGHT   the plausibility bound never fires
CAUGHT   the window length is unbounded
CAUGHT   in-window times are also rejected
3/3
```

The last one is the control doing the work: it is the **over-strict** direction, the failure the
original docstring explicitly warned about ("requiring all of them would reject honest labels"). No
refusal test would catch it — only the assertion that a length-plus-moment label still passes.

The new refusal test is parametrized over 0..1400, 1400..2800 and 2800..4162 rather than a window
chosen to make the rule work, which is the correction this finding is really about.

Gate: `VERIFY OK — 1142 passed, 0 skipped`.
