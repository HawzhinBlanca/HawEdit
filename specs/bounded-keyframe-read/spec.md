# Specification - bounded Stage 4 keyframe reads

- WHEN an extracted Stage 4 image is larger than the declared per-frame ceiling, THE keyframe
  extractor SHALL stop reading after one byte beyond the ceiling and refuse it as a
  `KeyframeError`.
- WHEN an extracted Stage 4 image is empty, THE keyframe extractor SHALL refuse it as a
  `KeyframeError`.
- WHEN an extracted Stage 4 image is exactly at the ceiling, THE keyframe extractor SHALL accept
  it and construct the same `JudgeFrame` contract.
- WHEN an extracted image is refused, THE keyframe extractor SHALL remove its uniquely owned
  private extraction directory through the existing cleanup path.
- WHEN a caller constructs `JudgeFrame` directly, THE judge contract SHALL enforce the same
  authoritative ceiling independently.

Acceptance tests:

- `test_keyframe_reader_limits_the_single_read_to_one_byte_past_the_ceiling`
- `test_keyframe_reader_accepts_a_payload_exactly_at_the_ceiling`
- `test_oversized_and_empty_extracted_keyframes_are_domain_failures_and_cleaned`
- `test_a_keyframe_over_the_inline_data_ceiling_is_refused`
