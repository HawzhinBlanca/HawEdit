# EARS Specification

| Criterion | Requirement | Named test |
| --- | --- | --- |
| C1 | WHEN unchanged single greedy generation returns its original prompt and a natural EOS before the cap, THE observer SHALL return the original object unchanged. | test_qwen_observer_admits_original_natural_eos |
| C2 | WHEN generation is unobserved, malformed, empty, capped, missing EOS, foreign-prefix or repeated, THE observer SHALL refuse before text admission. | test_qwen_observer_refuses_invalid_sequences, test_qwen_observer_requires_one_generation |
| C3 | WHEN sampling/beams/forced tokens/custom stop/configuration or generation identity is unsupported or changes, THE observer SHALL refuse and restore its temporary binding on every exit. | test_qwen_observer_refuses_configuration, test_qwen_observer_refuses_mutation, test_qwen_observer_restores_after_exception |
| C4 | WHEN production runtime/source/type contracts are unvalidated, THE validator SHALL refuse before model loading or text-only admission. | test_qwen_public_validator_refuses_unvalidated_dependency |
| C5 | WHEN old canonical text lacks the validator policy, THE store SHALL refuse reuse and preserve original raw/normalised/provenance bytes. | test_qwen_policy_refuses_legacy_canonical_cache |
| C6 | WHEN resumed operations lack or change the validator policy, THE journal SHALL refuse before cached text can be consumed and preserve original records. | test_qwen_policy_refuses_legacy_operation_journal |
| C7 | WHEN production is native or WSL, THE canonical admission policy SHALL include identical draft and validator guards without attesting fake producers. | test_native_and_source_bound_wsl_producers_share_admission_policy |

All criteria are engineering controls, not speech/editorial acceptance. Genuine
admitted SDK consumer and bad-region acoustic/native-editor checks remain open.

C3 includes assisted generation (prompt lookup/assistant early exit) and DoLa,
which are not greedy despite one beam and no sampling. C5/C6 also cover v1-to-v2
history via test_qwen_v2_policy_preserves_and_refuses_v1_canonical_cache and
test_qwen_v2_policy_preserves_and_refuses_v1_operation_journal. No old bytes are
rewritten or relabelled with the new policy.
