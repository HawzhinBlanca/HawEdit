# Spec: Face-Aware Caption Placement (Task T2.7)

## Acceptance Criteria (EARS Format)

- **AC-1 (Band Intersection Detection)**:
  WHEN a face vertical span `[top_y, bottom_y]` intersects the bottom caption band `[1300, 1650]`,
  THE system SHALL detect the collision.

- **AC-2 (Top Placement on Overlap)**:
  WHEN a caption event overlaps in time with a face intersecting the bottom caption band,
  THE system SHALL assign the event to the top caption style (`KurdishTop` with `alignment=8` and `margin_v=240`).

- **AC-3 (Bottom Placement on Clear Band)**:
  WHEN a caption event does not overlap in time with any face intersecting the bottom caption band,
  THE system SHALL assign the event to the default bottom caption style (`Kurdish` with `alignment=2` and `margin_v=360`).

- **AC-4 (Pixel Separation)**:
  WHEN an event with top placement is rendered through libass at 1080x1920 PlayRes,
  THE rendered subtitle ink extent SHALL remain strictly above Y=600 px, preventing any overlap with the lower frame.
