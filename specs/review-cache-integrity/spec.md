# EARS Specification

| Criterion | Named regression |
| --- | --- |
| WHEN a retained candidate MP4 differs from its measurement, THE pipeline SHALL visibly refuse reuse and preserve every existing artifact. | test_private_cache_refuses_changed_mp4_without_overwriting |
| WHEN any required member is absent, THE pipeline SHALL refuse reuse without inventing dimensions, duration or completion. | test_private_cache_refuses_missing_member_without_overwriting |
| WHEN measurement JSON is malformed, noncanonical, stale or fabricated, THE pipeline SHALL refuse reuse using bounded parsing and current independent observations. | test_private_cache_refuses_invalid_measurement; test_private_cache_refuses_malformed_measurement_blocks |
| WHEN clip or edit-plan identity/source/interval differs, THE cache inspector SHALL refuse the mismatched packet. | test_private_cache_refuses_mismatched_packet_binding |
| WHEN valid unchanged candidates are selected again, THE pipeline SHALL retain their exact bytes and report fresh measured physical fields while still awaiting review. | test_private_cache_reuses_unchanged_real_media_without_rewriting; test_distinct_selections_do_not_overwrite_each_others_deliveries |
| WHEN existing candidate storage is nonprivate or linked, THE cache inspector SHALL refuse it without repairing prior storage. | test_private_cache_refuses_hardlinked_member |

No returned measurement/result authorizes publication. Exact reviewed bytes still
require the existing authenticated serving-time reconciliation. This specification
does not claim full render-input equivalence, editorial-quality or release acceptance.
