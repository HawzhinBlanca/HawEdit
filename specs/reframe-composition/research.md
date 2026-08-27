# Research — vertical composition

## The symptom, measured

Two clips rendered from the same pipeline on 2026-08-27, both 1080x1920, both delivered:

| | crop_target | what the frame shows |
|---|---|---|
| `work/ep01-ship` | `static_centre` | empty wall and table centred; both speakers cut off at the edges |
| `work/ep01-face` | `face_tracked` | subject centred and legible; crop follows the action |

`--face-reframe` is opt-in, so the first is what the documented invocation produces.

## Where faces actually sit

OpenCV frontal + profile cascades (both facings), 60 samples per source, 20 s apart.

| source | detections | face centre | face height | channel |
|---|---|---|---|---|
| `ep10-0zC2bd03stw` | 246 | **33% down** | **28.5%** of frame height | `UC7jbpjdftJ61wV5cKGr9axg` (the owner's) |
| `01-MmQ9XPggSig` | 309 | 45% down | **11.6%** | `UCyULE_OfQlJAOi4eLKfUzIg` (a different channel) |

Both 1920x1080. The owner's own footage is already composed on the rule-of-thirds line with a
face filling more than a quarter of the frame. **The headroom complaint comes from the wide
shot, and that video is not the owner's.**

## Why `y` is currently always 0

`vertical_crop_size` gives `crop_h = min(source_height, source_width / (9/16))`. For any 16:9
source that is the full height, so `crop_filter`'s `y = (source_height - crop_h) // 2` is 0.
There is no vertical crop to place. Framing the subject vertically therefore *requires* taking
less than the full height — which is a zoom, and this source is 1920x1080 at ~850 kbps already
upscaled 1.78x to reach 1920 tall.

## Symbols

| symbol | file | note |
|---|---|---|
| `FocusPoint` | `reframe.py:59` | `at_ms`, `center_x` only — the tracker computes `y`/`h` and discards them |
| `OpenCvFaceTracker.track` | `reframe.py:187` | has the full `(x, y, w, h)` box |
| `choose_face` | `reframe.py:152` | already prefers a large face |
| `stabilize` | `reframe.py:249` | hysteresis + median on `center_x` |
| `crop_filter` | `render.py:295` | `y` hardcoded to the centre |
| `vertical_crop_size` | `render.py:265` | shared with the stabilizer's dead zone |

37 `FocusPoint(...)` construction sites and 19 `crop_filter(...)` calls across `src` and
`tests`, so any new field has to be optional with a `None` default — `None` meaning unmeasured
rather than zero, as D-033 established for `payoff_at_ms`.

## Risks

- **Zoom costs resolution and this footage has none to spare.** 1080 -> 1920 is already 1.78x.
  Bringing an 11.6% face to 22% needs a further 1.9x, i.e. 3.4x total on 850 kbps source.
- **A blanket zoom would damage the good case.** ep10 at 28.5% and 33% down needs nothing; any
  unconditional tightening makes the owner's own footage worse.
- `Reframe.SPEAKER_TRACKED` is still blocked on diarization (`BLOCKED.md` #4), so a face-tracked
  default follows the dominant face rather than the person talking.
- Face tracking needs OpenCV (the media extra). Making it the default means a missing dependency
  must degrade visibly, not silently.
