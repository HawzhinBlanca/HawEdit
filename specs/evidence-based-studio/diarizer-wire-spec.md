# Pinned Diarizer Wire EARS

Extends parent T3, BLUEPRINT section3 Stage0/section7 and D-252/D-276, preserving the
direct converter and production exclusive-turn requirements of D-243.

| ID | Requirement | Named regression |
|---|---|---|
| DW1 | WHEN the pinned producer returns a wrapped result, THE adapter SHALL convert its explicit exclusive annotation, not the wrapper or ordinary annotation. | test_wrapped_result_selects_only_explicit_exclusive_turns |
| DW2 | WHEN the result lacks an exclusive annotation, THE adapter SHALL refuse with an actionable exclusive-output error even if ordinary tracks exist. | test_missing_or_malformed_exclusive_output_never_falls_back |
| DW3 | WHEN the explicit annotation does not expose a callable itertracks member, THE adapter SHALL refuse rather than invent empty output. | test_missing_or_malformed_exclusive_output_never_falls_back |
| DW4 | WHEN exclusive output is legitimately empty, THE adapter SHALL return an empty tuple without substituting ordinary speaker turns. | test_empty_exclusive_output_does_not_invent_ordinary_turns |
| DW5 | WHEN the configured adapter runs, THE adapter SHALL preserve the selected local checkpoint, actual audio path and configured device. | test_configured_model_audio_and_device_reach_the_producer |
| DW6 | WHEN wrapped exclusive turns round to invalid durations or overlap, THE converter/attachment SHALL retain their existing refusal without merging or repairing turns. | test_wrapped_turns_keep_rounding_and_overlap_refusals |
| DW7 | WHEN wrapped exclusive turns exceed the media clock, THE shared attachment SHALL refuse them rather than clamp the output. | test_wrapped_turns_outside_media_clock_are_refused |
| DW8 | WHEN weights or the optional runtime are unavailable, THE adapter SHALL retain the existing contextual availability refusal. | test_absent_weights_are_refused_by_naming_blocker_four; test_missing_pyannote_is_reported_as_a_missing_extra |

No tuple/signature/style/model substitution and no canonical ASR mutation. Completed
delivery remains authenticated publication, not this adapter output or pipeline report.
Wire controls are not real-model/runtime/licence/DER or independent acceptance evidence.
