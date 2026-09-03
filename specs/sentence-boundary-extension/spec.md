# Specification: Sentence Boundary Extension (Task T4.8)

## Acceptance Criteria (EARS Format)

### AC-1: Sentence Completion Absorption
WHEN a fused boundary `[final_in_ms, final_out_ms]` includes words not in `selected`,
AND every touched candidate sentence has all of its words entirely contained within `[final_in_ms, final_out_ms]`,
AND the candidate sentences are contiguous with `selected`,
THE system SHALL absorb the candidate sentences into `selected`, including all their words in `clip_words`, caption generation, and transcript.

### AC-2: Incomplete Sentence Refusal
WHEN a fused boundary `[final_in_ms, final_out_ms]` includes words not in `selected`,
AND any touched candidate sentence has words falling outside `[final_in_ms, final_out_ms]`,
THE system SHALL refuse the boundary expansion and yield `StageSkipped(stage="boundary", blocked_by=("uncaptioned speech",))`.

### AC-3: Editorial Transcript Integrity
WHEN candidate sentences are absorbed under AC-1,
THE system SHALL ensure that `_raw_text_for_words` and `build_ass` cover the extended sentence set so zero audible words in the rendered media are missing from the captions or contract transcript.
