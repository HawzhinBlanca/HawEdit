# Retained Render Request EARS

- RI1: WHEN a retained candidate lacks a current render-request binding or its
  binding differs from reconstructed inputs, THE pipeline SHALL refuse reuse,
  preserve all prior bytes, and report the need for a new revision/work directory.
  Tests: `test_private_cache_refuses_changed_render_controls`,
  `test_private_cache_refuses_missing_or_changed_request_binding`.
- RI2: WHEN identical inputs and unchanged decoded private media are rechecked,
  THE pipeline SHALL retain the preview without rewriting or publishing it.
  Test: `test_private_cache_reuses_unchanged_real_media_without_rewriting`.
- RI3: WHEN headline text is changed in a new immutable work directory, THE
  pipeline SHALL render new bytes with visibly different decoded frames while
  preserving canonical transcript text and the previous candidate.
  Test: `test_headline_revision_changes_decoded_pixels_and_preserves_original`.
- RI4: WHEN asset content changes at the same path or structured input is invalid,
  THE identity builder SHALL change the digest or refuse rather than invent an
  equivalent request. Tests: `test_render_identity_binds_same_path_asset_bytes`,
  `test_render_identity_refuses_unsupported_or_nonfinite_inputs`.
- RI5: WHEN input or asset identity changes during render/reuse, THE pipeline
  SHALL refuse freezing/accepting the candidate; unchanged request hashes SHALL
  NOT count as authenticated editorial approval or completed publication.
  Test: `test_pipeline_refuses_asset_changed_after_real_render`, plus real
  pipeline publication/review suites and identity stable-open tests.
- RI6: WHEN reading a legacy Provenance block, THE contract SHALL preserve
  readability without attributing a render-request binding; malformed bindings
  SHALL be refused. Test: `test_render_identity_provenance_is_optional_and_strict`.
- RI7: WHEN unchanged retained media with an internal silence trim is replayed,
  THE pipeline SHALL return its exact stored editing metadata and plan-derived
  requested output duration, preserving original packet and canonical transcript
  bytes. Tests: `test_private_cache_returns_retained_editing_metadata`,
  `test_private_cache_returns_retained_output_duration`.
- RI8: WHEN unsigned legacy QC metadata changes without a pixel-input change,
  THE pipeline SHALL retain unchanged renderable private media without treating
  that metadata as approval or authorizing publication. Tests:
  `test_private_cache_retains_preview_without_unsigned_qc_promotion`, existing
  `test_unreviewed_render_is_retained_privately_for_review` and signed review/
  publication suites. Renderability refusals remain separately enforced.
