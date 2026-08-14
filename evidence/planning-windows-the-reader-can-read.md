# Planning windows the reader can actually read

> Measured 2026-08-09 on hawapc01 against `0758b84`.
> Source: `ZAR38MinTest.mp4` — 640×360 h264, 25 fps, 2313.8 s.

D-138 measured the constraint: on a 23.99 GiB 3090 Ti, `MCG-NJU/VideoChat3-4B` reads at most **8**
frames per window, and the demand is quadratic. BLOCKED #17 refused the two easy responses — lowering
§3's `MAX_FRAMES_PER_WINDOW`, and truncating a planned window at read time — leaving one: plan smaller
windows.

## The change

`plan_scene_windows(..., max_frames=MAX_FRAMES_PER_WINDOW)`, exposed as `--visual-max-frames`. The
default is §3's ceiling, so no machine inherits another's limit. Both bounds are derived from constants
already recorded: above §3's ceiling a plan would exceed the published setting; below
`TEMPORAL_PATCH_FRAMES` a window cannot fill one temporal patch and the processor would pad it by
repeating a frame that was never filmed (D-060).

## The cost, measured

```
real media, 2,313,800 ms at 2 fps, no cuts:
  ceiling 64  ->  73 windows, longest 31,696 ms
  ceiling  8  -> 579 windows, longest  3,997 ms
```

7.9× the windows, each seeing an eighth of the context. §8.2's Recall@K is then measured on a different
retrieval unit than §3 describes. Recorded as a cost, not sold as a win.

## Proven on the real file

```
$ hawedit ZAR38MinTest.mp4 --visual --visual-max-frames 8 --visual-keep 7 …

visual_windows planned : 641
indexed_windows        : 641
retrieved              :  50      (§3's RETRIEVE_K)
survivors              :   7      (inside §3's 5..10)
candidate_ids          :   7
GPU 0 / GPU 1          : 17,881 MiB each — no CUDA OOM
```

`visual_index` **ran** rather than skipping, for the first time on real media: Stage 2's frame
extraction, Qwen embedding, retrieval and reranking, then VideoChat3 reading all seven survivors. No
stub anywhere in that path. Editorial, boundary, render and delivery remain skipped, each naming Stage
4's absent judge — `BLOCKED.md` #3, Hawa's.

## Mutation audit

```
baseline FAILED=0
CAUGHT   the plan ignores the ceiling it was given (the defect)        FAILED=3
CAUGHT   any ceiling is accepted, including above §3's                 FAILED=2
CAUGHT   the default silently becomes one machine's limit              FAILED=6
CAUGHT   the pipeline drops the flag on the floor                      FAILED=1
CAUGHT   the CLI value never reaches run_pipeline                      FAILED=1

5/5
```

The last two **survived the first audit**, for exactly D-137's reason one iteration earlier: the planner
was tested and the trip from the CLI was not. Both replacements assert the windows the run *reports*,
not the argument it was handed.

**A premise of mine that was wrong**, kept because the correction is the useful part: the first version
capped the fixture at 2 frames, but its 1400 ms scenes already plan exactly 2 at 1 fps, so the cap
changed nothing and the test asserted a difference that could not exist. At 2 fps those scenes plan 3,
which a ceiling of 2 genuinely splits.

Gate: `VERIFY OK — 1217 passed, 0 skipped`.
