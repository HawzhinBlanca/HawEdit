# M5.3 — §3 Stage 3 Path B, and the SV6D check that was measuring a regex

`src/hawedit/path_b.py` · `src/hawedit/clip.py` ·
`tests/test_path_b.py` (26 tests) · `tests/test_pipeline.py` · D-039

## The finding

§3 Stage 3 sets the output schema and the rule that goes with it:

> **Prompt schema — SV6D.** … `subject · aesthetics · camera language · editing · narrative ·
> retention`. Every label must cite a timestamp. **Reject output where a claim has no timeline
> evidence.**

`Sv6d` has enforced the first sentence since M2.2 by searching each label for something that
looks like a time. It could enforce only that, because the type does not know which scene it
describes:

```
scene shown to the model : 300000 .. 312000 ms
label                    : 'speaker gestures at 9999s'
cited                    : (9999000,) ms  = 2.7775 hours
Sv6d presence check      : PASSED (constructed)
range check              : REFUSED
   SV6D subject label 'speaker gestures at 9999s' cites [9999000] ms, all outside the scene
   it describes (300000..312000 ms)
```

Two and three-quarter hours cited about a twelve-second scene. Regex satisfied, constructor
returns, claim anchored to a moment the model was never shown. "Reject output where a claim has
no timeline evidence" was being read as "reject output with no *string that looks like*
timeline evidence" — shape substituted for content, again.

`assert_sv6d_within_window` is the other half, and it lives beside the type rather than inside
it because it needs the window as an argument — the same split as `assert_boundary_invariant`
beside `Boundary`. Every `SceneReading` runs through it at construction.

**The rule is that *some* cited time lands in the window, not that every number does.** A label
may mention a length as well as a moment: "slow push-in over 3s, starting 5:04" cites 3 000 ms
and 304 000 ms, and only the second is a point on the timeline. Requiring all of them would
reject honest labels; requiring none is what let `9999s` through. A label citing only "over 3s"
anchors nothing and is refused.

## The frame budget

> **VideoChat3-4B notes:** … Segmentation is mandatory: the authors report ~17.7 GB at 256
> frames and ~26.7 GB at 512.

Five 64-second scene windows are 320 frames. The 256-frame figure governs one invocation, not
the whole episode, so they are packed deterministically into calls of 256 and 64 frames. A test
asserts every call stays inside the ceiling. The earlier implementation refused the 320-frame
episode outright, accidentally turning a VRAM limit into a maximum source length (D-059).

## The join, on real media

Path B reads the windows Stage 2 planned from Stage 0's own cuts on this video, and the union
runs two-sided:

```
windows : (0, 1400), (1400, 2800), (2800, 4162)     <- from this run's shot cuts
verbal  : one candidate at 0..1700
merged  : BOTH for the overlapping moment, VISUAL for the rest — 4 sources, nothing dropped
```

`run_pipeline(..., read_scenes=…)` is the seam: supply a `VideoUnderstanding` and §3's union
stops being one-sided. Without one it stays one-sided, which §3 says is correct rather than
degraded — "Candidates from either path proceed".

## What this does not show

This evidence row originally used a fake reader. The real model and measured prompt now live in
`evidence/m5-4-path-b.md`; the remaining integration gaps are recorded there and in `README.md`.
