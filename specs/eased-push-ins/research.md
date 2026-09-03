# Research: Eased Push-Ins (Task T2.6)

## 1. Problem & Context
HawEdit currently implements framing dynamics via `punch_in_schedule` (`src/hawedit/render.py:591-640`).
It identifies pause boundaries (`cut_points_ms`) of at least `CUT_PAUSE_MS` (120 ms) and selects boundaries separated by `MIN_SHOT_MS` (3,000 ms), avoiding source cuts by `SHOT_CUT_GUARD_MS` (1,500 ms).
For each kept boundary, it alternates the zoom factor between `1.25` and `1.0`.
In `crop_filter`:
```python
commands = ";".join(
    f"{at_ms / 1000:.3f} crop w {max(2, int(crop_w / factor)) // 2 * 2};"
    f"{at_ms / 1000:.3f} crop h {max(2, int(crop_h / factor)) // 2 * 2}"
    for at_ms, factor in punch_ins
)
```
This produces instantaneous, mechanical square-wave jumps (e.g. 1.00x -> 1.25x -> 1.00x) that feel robotic and abrupt during speech.

In professional video repurposing (and viral reels), pacing is driven by **slow continuous push-ins**:
- The camera slowly glides inward (1.00x -> 1.08x) over the course of a spoken shot, maintaining visual energy and viewer retention.
- Hard cuts are preserved strictly at motivated boundaries: source camera cuts and natural pause breaks.
- At each boundary, the camera cuts hard (snaps back to wide or another angle) and begins the next subtle push-in.

## 2. Technical Grounding & FFmpeg Mechanics
FFmpeg's `crop` filter evaluates `w` and `h` once at filter graph configuration, but supports runtime modification of `w` and `h` via `sendcmd`.
Testing on Windows with FFmpeg 8.1.1-full confirms:
1. `sendcmd` accepts time-stamped commands:
   `sendcmd=c='0.000 crop w 608;0.000 crop h 1080;0.100 crop w 604;0.100 crop h 1072;...'`
2. Emitting keyframes at 100 ms intervals (10 fps) generates smooth, fluid motion without overwhelming the FFmpeg parser or inflating memory.
3. Smoothstep easing ($S(p) = 3p^2 - 2p^3$) gives organic acceleration and deceleration:
   - Starts gently from $p = 0$.
   - Glides steadily through the middle of the phrase.
   - Decelerates softly towards $p = 1.0$ at the end of the shot.
4. When paired with `FACE_COMPOSITION_LINE = 0.38`, the face remains pinned to the golden composition line while the frame pushes in.

## 3. Mathematical Formulation
For each shot span $[T_{start}, T_{end}]$ with duration $D = T_{end} - T_{start}$:
For each step $t \in [T_{start}, T_{end}]$ at step interval $\Delta t = 100$ ms:
- Progress: $p = \frac{t - T_{start}}{D} \in [0.0, 1.0]$
- Ease: $E(p) = 3p^2 - 2p^3$
- Zoom factor: $Z(t) = Z_{start} + (Z_{end} - Z_{start}) \cdot E(p)$
  where $Z_{start} = 1.00$ and $Z_{end} = 1.08$.
At $T_{end}$, if followed by another shot, the next shot starts at $Z_{start} = 1.00$, producing an instantaneous hard cut at the shot boundary.

## 4. Architectural Integration
- `shot_spans(boundaries_ms, clip_duration_ms, source_cuts_ms=(), min_shot_ms=MIN_SHOT_MS, guard_ms=SHOT_CUT_GUARD_MS) -> tuple[tuple[int, int], ...]`:
  Computes continuous shot intervals partitioned by kept pauses and source cuts.
- `eased_push_schedule(shot_spans, push_zoom=1.08, step_ms=100, alternating=False) -> tuple[tuple[int, float], ...]`:
  Produces `(at_ms, factor)` keyframe tuples directly compatible with `crop_filter`.
- CLI & Pipeline flag `--eased-push`:
  Allows opting into eased push-ins or running comparison renders for editor taste evaluation.
