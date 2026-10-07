# EARS Specification

| Criterion | Requirement | Named regression |
| --- | --- | --- |
| VM-01 | WHEN compatible complete decoded reference media and libvmaf are available, THE optional probe SHALL report the native JSON-pooled mean, not a regex guess. | test_vmaf_matches_native_pooled_observations |
| VM-02 | WHEN decoded pixels are deliberately damaged, THE observation SHALL follow their real native report, not a fixed score. | test_vmaf_degraded_decoded_pixels_score_below_reference |
| VM-03 | WHEN decoded clocks/frame count/geometry/pixel format are incompatible, THE probe SHALL return unknown without repeated or partial-reference scoring. | test_vmaf_refuses_partial_or_incompatible_reference |
| VM-04 | WHEN inputs/tools/reports are missing or failed, THE optional probe SHALL return unknown and preserve input bytes. | test_vmaf_refuses_absent_input_or_tool |
| VM-05 | WHEN raw observations are malformed, nonfinite, out of domain, incomplete, misindexed or inconsistent, THE parser SHALL refuse them without a fallback number. | test_vmaf_invalid_observation_is_refused |
| VM-06 | WHEN decoded timeline records are missing, malformed or nonmonotonic, THE parser SHALL refuse inferred frame clocks. | test_vmaf_invalid_timeline_is_refused |
| VM-07 | WHEN measure_clip receives an explicit compatible reference, THE caller SHALL retain the actual optional observation while leaving undefined global PSNR unknown. | test_vmaf_measured_reference_runs_through_measure_clip |

None is unknown, not quality approval. No meaning/caption/speaker/editorial or
authenticated publication requirement is satisfied by VMAF alone.
