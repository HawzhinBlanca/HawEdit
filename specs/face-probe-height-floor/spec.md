# Spec — face probe height floor

EARS criteria. Each names the test that will be cited in `tasks.md`.

- **AC1** WHEN the delivery face probe gets a detection whose box is shorter than 5 % of the
  frame height, THE probe SHALL NOT count that sample as containing a face, and SHALL leave the
  box out of `median_face_height_share`, `median_y_center_share` and `first_frame_face_share`.
  `tests/test_measure.py::test_a_detection_below_the_height_floor_is_not_a_face`
- **AC2** WHEN a detection's box is 5 % of the frame height or taller, THE probe SHALL count it
  exactly as it does today.
  `tests/test_measure.py::test_a_detection_at_the_height_floor_is_a_face`
- **AC3** WHEN the frontal cascade returns only boxes under the floor, THE probe SHALL still try
  the profile cascades before deciding the sample has no face.
  `tests/test_measure.py::test_an_undersized_frontal_box_does_not_stop_the_profile_fallback`
- **AC4** WHEN a `face_tracked` render contains no face, THE pipeline SHALL NOT publish it and
  SHALL report `face_tracking_unsubstantiated` with a measured share of 0.0, while the clip
  still claims `face_tracked` and not `speaker_face`.
  `tests/test_pipeline.py::test_ambiguous_speaker_tracking_falls_back_without_claiming_speaker_provenance`
