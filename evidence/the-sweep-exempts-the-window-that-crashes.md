# The sweep exempts the window that crashes, and refusing it is worse

`BLOCKED.md` #22 recorded that `--visual-fps 1.0` dies inside the reader with
`t:1 must be larger than temporal_factor:2`, and said the minimum frame count must be read from
the §7 checkpoints rather than guessed. This is that reading, the root cause, and an attempted fix
that was **reverted** because it is worse than the defect.

## The number, read not guessed

`models/MCG-NJU__VideoChat3-4B/video_preprocessor_config.json`:

```json
{"do_sample_frames": true, "fps": 2, "min_frames": 4, "temporal_patch_size": 1,
 "temporal_merge_size": 4, "max_frames": 1024, "patch_size": 14}
```

`fps: 2` is where `DECLARED_SAMPLING_FPS = 2.0` comes from, and `min_frames: 4` matches the
existing `_MIN_SAMPLED_FRAMES = 4`. Both constants are already justified against the checkpoints.

## The root cause, reproduced with no GPU

`plan_scene_windows` on the real file's own Stage 0 output (138 cuts, 2 313 800 ms):

| rate | windows | below `min_frames: 4` | smallest |
|---|---|---|---|
| 2.0 fps — the declared rate, every run so far | 641 | **1** | `s22:w0`, 1000 ms → **2** frames |
| 1.0 fps | 364 | **31** | `s22:w0`, 1000 ms → **1** frame |

The 1-frame window is the crash: `t:1`.

**And the sweep that appears to rule this out exempts it.**
`tests/test_video_input.py::test_every_plannable_window_is_delivered_to_the_model_whole` claims
*"every window a planner can produce is delivered whole"*, and its body contains:

```python
emitted = math.floor(window.duration_ms * window.fps / 1000)
if emitted < 2:
    continue          # <- the failing case, skipped
```

Running the sweep's own arithmetic on the real counterexamples:

```
2 frame(s) @ 2.0 fps -> model reads 2   WHOLE
1 frame(s) @ 1.0 fps -> model reads 2   *** NOT WHOLE ***
2 frame(s) @ 1.0 fps -> model reads 2   WHOLE
```

So the claim is true only of the windows the sweep did not skip, and the real 38-minute file
produces the skipped one.

## The fix that was tried, and why it was reverted

`SceneWindow.__post_init__` already refuses the **upper** bound (`frame_count >
MAX_FRAMES_PER_WINDOW`); the symmetric lower bound looked obviously right:

```python
if self.frame_count < TEMPORAL_PATCH_FRAMES:
    raise VisualIndexError(...)
```

Measured, it did exactly what #22 asked: 2.0 fps unaffected (641 windows, minimum 2 frames), and
1.0 fps **refused at plan time** naming the window — instead of dying inside the model after
Stage 0 and a full re-embed.

**It also broke two existing tests, and they were right.** `plan_scene_windows` defaults to
`REFERENCE_FPS = 1.0`, so at the default rate *any scene shorter than 2 s cannot be planned at
all* — an ordinary 1-second tail scene makes planning fail outright. Worse, §3 requires windows to
**tile** the media; `assert_window_coverage` exists because "a hole here makes a moment invisible
to Path B", and refusing a short scene is exactly such a hole. Trading a padded frame for missing
footage is the wrong trade, and the guard was reverted — `visual_index.py` is unchanged.

## What actually has to be decided

A scene shorter than one temporal patch has no good handling, and the three candidates have
opposite failure modes — which is why this is recorded rather than chosen:

1. **Let it through** (today). The processor pads by repeating the last frame, so the model reads
   a frame that was never filmed and the embedding is, in this module's own words,
   "indistinguishable from an honest one". Silent, and it is what every run so far has done — once,
   at 2.0 fps.
2. **Merge the short scene into its neighbour.** Keeps coverage, but the window then spans a shot
   cut, which is the one boundary §3 Stage 2 segments on.
3. **Extend the window past the scene.** Keeps coverage and frame count, and embeds footage the
   window does not claim.

None is free, none is measurable without deciding what a window is *for*, and this loop does not
guess. `BLOCKED.md` #22 refreshed with the measurement and the three options.

**Left unfixed deliberately:** the sweep's `if emitted < 2: continue`. Removing the exemption
would turn the sweep red against real planner output, which is honest — but it would be red with
no fix available, and a permanently red gate is not a signal. It is named in #22 instead, so the
exemption cannot be read as coverage.
