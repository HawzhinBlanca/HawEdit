# Tasks ledger — reframe-composition
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  Face tracking is the default and `--static-crop` opts out; a missing OpenCV degrades
          to static centre visibly rather than silently.
                                  (tests: test_face_tracking_is_the_default,
                                          test_static_crop_opts_out_and_is_recorded,
                                          test_a_missing_face_tracker_degrades_visibly)

- [x] T2  `FocusPoint` carries the measured face box, and `crop_filter` places the crop
          vertically from it — leaving a well-composed source alone.
                                  (tests: test_a_well_framed_source_is_not_zoomed,
                                          test_a_small_face_is_tightened_to_the_composition_line,
                                          test_an_unmeasured_focus_point_crops_as_it_always_did)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
