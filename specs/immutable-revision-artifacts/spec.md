# EARS

- WHEN an existing revision identifier is committed again, THE revision system
  SHALL refuse while preserving original record bytes, including terminal ones.
  Tests: test_two_commits_under_the_same_id_overwrite_the_prior_record (historical
  name retained, assertion now stronger), test_caption_revision_id_is_immutable.
- WHEN a final ASS/MP4/SRT/EDL path is occupied, THE renderer SHALL refuse before
  changing any original record or artifact. Tests:
  test_caption_revision_preserves_occupied_artifacts,
  test_boundary_revision_preserves_occupied_artifacts.
- WHEN another attempt publishes MP4 after preflight, THE losing renderer SHALL
  preserve the competing bytes and report failure rather than deleting them.
  Tests: test_caption_revision_preserves_competing_mp4,
  test_boundary_revision_preserves_competing_mp4.
- WHEN another attempt publishes SRT during encoding, THE renderer SHALL retain
  it and the real private MP4, report missing delivery sidecars, and retain the
  requirement for fresh review. Tests:
  test_caption_revision_preserves_competing_srt,
  test_boundary_revision_preserves_competing_srt.
- WHEN a revision is rendered successfully, THE system SHALL continue to burn
  the requested real style/span with valid clocks and invalidate prior QC.
  Existing real-media style/boundary/re-review tests remain required unchanged.
- WHEN a previous render claim exists, THE system SHALL refuse replay without
  changing it or the revision record. Tests: test_caption_revision_retains_render_claim,
  test_boundary_revision_retains_render_claim.
- WHEN two callers concurrently render the same pending revision, THE system
  SHALL admit exactly one writer and preserve the successful final record.
  Tests: test_caption_revision_has_one_render_owner,
  test_boundary_revision_has_one_render_owner.

BLUEPRINT4.3.6/8.3, D-263/D-277 and the original full acceptance requirements
remain intact. These private outputs are not authenticated published deliverables.
