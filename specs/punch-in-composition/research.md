# Research — Composition Line Under Punch-Ins (`specs/punch-in-composition`)

> Task T2.4 from `specs/pro-grade-program/tasks.md`.
> Root cause analysis and mathematical proof for vertical face placement under dynamic punch-in reframing.

---

## 1. Problem Statement & Root Cause
In vertical video reframing (9:16 portrait), standard framing rules and `BLUEPRINT.md` §3 require the subject's eye level / face center to sit on the upper-third composition line:
`FACE_COMPOSITION_LINE = 0.38`.

In `src/hawedit/render.py`:
1. Static vertical framing (`vertical_crop` / `vertical_framing` at line 431) implements this correctly:
   ```python
   y = max(0, min(face_center_y - int(FACE_COMPOSITION_LINE * crop_h), source_height - crop_h))
   ```
   Here, `face_center_y - y = 0.38 * crop_h`. The face sits at 38% from the top of the cropped window.

2. Dynamic punch-ins in `crop_filter` (lines 563–565):
   ```python
   centre_y = face_center_y if face_center_y is not None else source_height // 2
   x_expr = f"min(max({centre_x}-out_w/2\\,0)\\,in_w-out_w)"
   y_expr = f"min(max({centre_y}-out_h/2\\,0)\\,in_h-out_h)"
   ```
   Notice: `y_expr` uses `out_h/2`!
   This forces the crop window to vertically center on the face (`face_center_y - y = 0.50 * out_h`).
   Whenever dynamic punch-ins occur on a face-tracked clip, the subject's face suddenly drops 12% downward toward the dead center of the screen, creating an amateurish visual jump.

---

## 2. Mathematical Solution & FFmpeg Filter Grammar
In ffmpeg's `crop` filter expression syntax:
- `in_w`, `in_h`: input frame dimensions.
- `out_w`, `out_h`: current cropped output width and height (updated per-frame via `sendcmd` commands).

When `face_center_y is not None`:
We want the face center to satisfy:
$$\text{face\_center\_y} - y = \text{FACE\_COMPOSITION\_LINE} \times \text{out\_h}$$
$$y = \text{face\_center\_y} - \text{FACE\_COMPOSITION\_LINE} \times \text{out\_h}$$

Clamping within `[0, in_h - out_h]`:
```python
y_expr = f"min(max({face_center_y}-{FACE_COMPOSITION_LINE}*out_h\\,0)\\,in_h-out_h)"
```

When `face_center_y is None`:
Default to vertical centering:
```python
centre_y = source_height // 2
y_expr = f"min(max({centre_y}-out_h/2\\,0)\\,in_h-out_h)"
```

---

## 3. Grounding & References
- `src/hawedit/render.py`: `FACE_COMPOSITION_LINE = 0.38` (line 34).
- `tests/test_render.py`: `test_wide_shot_tightening_preserves_the_composition_line` verifies static framing against 0.38.
- `specs/pro-grade-program/tasks.md`: Task T2.4 requires unit test `test_a_punch_in_keeps_the_face_on_the_composition_line`.
