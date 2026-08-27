# Impact map — vertical composition

## `FocusPoint` — `reframe.py:59` — **gains two optional fields**

37 construction sites across `src/hawedit/diarization_acceptance.py`, `src/hawedit/reframe.py`,
`tests/test_pipeline.py`, `tests/test_reframe.py`. `center_y` and `face_height` default to
`None` — unmeasured, not zero (D-033) — so every existing site keeps working and AC-6 holds.

| caller | site | covered by |
|---|---|---|
| `OpenCvFaceTracker.track` | `reframe.py` | `tests/test_reframe.py` tracker suite |
| `stabilize` | `reframe.py` | `test_a_small_wobble_does_not_move_the_camera` and neighbours |
| `_steady_camera` | `pipeline.py` | `tests/test_pipeline.py` reframe wiring |

`stabilize` currently rebuilds points from `center_x`; it must carry the new fields through or
they are dropped between the tracker and the renderer.

## `crop_filter` — `render.py:295` — **gains vertical placement**

19 call sites in `src/hawedit/render.py`, `tests/test_render.py`, `tests/test_caption_timing.py`.
New parameters are keyword-only with defaults that reproduce `y = (source_height - crop_h) // 2`.

| caller | site | covered by |
|---|---|---|
| `render_clip` | `render.py` | `tests/test_render.py` filter-chain suite |

## CLI — `--face-reframe` inverts to `--static-crop`

`--face-reframe` is asserted in `_CLI_PREFLIGHT_CASES` and in the `--timelens` co-requirement at
`pipeline.py:2871`. Both move with it, and the flag's removal is itself a refusal case if an old
invocation passes it.

## Gap found

No test asserts anything about the *vertical* crop position: `y` has been
`(source_height - crop_h) // 2` since the function was written and is 0 for every 16:9 source, so
the expression has never been exercised with a non-zero result.
