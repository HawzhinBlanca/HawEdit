# Specification: Hook Taxonomy, Payoff, and Loop Scoring (Task T4.4)

## Acceptance Criteria (EARS Format)

### AC-1: Hook Taxonomy Validation
WHEN a `JudgeVerdict` or `Editorial` object is constructed,
THE system SHALL require `hook_type` (if provided) to be one of `{"question", "claim", "contrast", "story_open", "confession"}`, rejecting invalid types with `ValueError`.

### AC-2: Payoff Strength & Beat Validation
WHEN a `JudgeVerdict` or `Editorial` object is constructed,
THE system SHALL require `payoff_strength` to be a finite JSON number in `[0.0, 1.0]` and `ends_on_a_beat` to be a boolean, rejecting out-of-range or invalid types with `ValueError`.

### AC-3: Kurdish Reason Preservation
WHEN a `JudgeVerdict` is constructed,
THE system SHALL require `reason_ckb` to contain Central Kurdish (Arabic script) text, validating it with `_kurdish_field`.

### AC-4: Contract Serialization & Backward Compatibility
WHEN `Editorial` or `JudgeVerdict` is serialized to dict or deserialized from dict,
THE system SHALL preserve existing legacy JSON documents without `hook_type`, `payoff_strength`, `ends_on_a_beat`, or `reason_ckb`, while round-tripping new fields when present.

### AC-5: Editorial Selection Tiebreaking
WHEN multiple candidate runs meet all shippable editorial criteria,
THE system SHALL rank them by `(verdict.hook_score, verdict.payoff_strength, verdict.ends_on_a_beat)` to select the highest-payoff clip.
