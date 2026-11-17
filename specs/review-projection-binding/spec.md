# EARS

| ID | Criterion | Named Automated Regression |
|---|---|---|
| RP1 | WHEN a review candidate's MP4 or measurement is hard-linked, THE studio SHALL refuse ready projection and preserve original evidence. | test_review_projection_refuses_hardlinked_evidence |
| RP2 | WHEN a report names a foreign candidate directory or mismatched MP4 basename, THE studio SHALL refuse ready projection. | test_review_projection_requires_exact_private_candidate_scope |
| RP3 | WHEN a measurement contains invalid schema/types, duplicate keys or nonfinite JSON, THE studio SHALL refuse ready projection without a duration/hash claim. | test_review_projection_requires_preview_measurement_contract |
| RP4 | WHEN stable real MP4 bytes match a valid measured record in their private candidate scope, THE studio SHALL retain awaiting-review and match the preview's measured size/hash/duration without claiming publication. | test_review_projection_matches_real_preview_evidence |
| RP5 | WHEN measurement bytes change during real MP4 hashing even with restored size/mtime, THE studio SHALL reopen the raw record and refuse ready projection. | test_review_projection_reopens_measurement_after_real_media_read |

These tests establish file/record binding, not native editorial quality or release.
