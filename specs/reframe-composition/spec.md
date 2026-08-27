# Specification — vertical composition

## Acceptance criteria

- **AC-1:** WHEN no crop flag is given, THE pipeline SHALL track faces and move the crop, because
  the static-centre default was measured producing a clip with both speakers cut off.
- **AC-2:** WHEN an operator wants the old behaviour, THE CLI SHALL accept `--static-crop` and
  record `static_centre` on the artifact.
- **AC-3:** WHEN face tracking is unavailable (no OpenCV), THE run SHALL fall back to a static
  centre crop and SHALL say so in the report, never silently.
- **AC-4:** WHEN the tracked face already fills at least the target share of frame height, THE
  crop SHALL take the full source height unchanged, so a well-composed source is not zoomed.
- **AC-5:** WHEN the tracked face is smaller than the target share, THE crop SHALL tighten
  vertically toward it, bounded by a named maximum zoom, and place the face centre at the
  composition line.
- **AC-6:** WHEN a focus point carries no vertical measurement, THE crop SHALL behave exactly as
  it does today, so every existing caller and artifact is unaffected.
