# Specification — candidate spans that can become clips

## Acceptance criteria

- **AC-1:** WHEN Path A is asked for candidates, THE prompt SHALL state the target clip duration
  range and require returned spans to fall inside it.
- **AC-2:** WHEN Path A returns spans, THE pipeline SHALL measure how many complied and record
  that, because an instruction to a model is a request rather than a guarantee.
- **AC-3:** WHEN a candidate is shorter than the target minimum, THE pipeline SHALL grow it
  outward to complete sentence boundaries until it reaches the target, rather than discarding it.
- **AC-4:** WHEN a candidate cannot be grown to the minimum without running out of complete
  sentences, THE pipeline SHALL record it as ineligible with that reason, and SHALL NOT judge it.
- **AC-5:** WHEN a candidate already falls inside the target range, THE pipeline SHALL leave its
  span unchanged.
- **AC-6:** WHEN a grown span is judged, THE verdict SHALL be recorded against the grown span,
  never the seed, so a stored verdict always describes the footage that was scored.
- **AC-7:** WHEN growth changes a span, THE rejection record SHALL still state the reason the
  code acted on — `_complete_sentences_within` is shared with `_rejected_candidates` precisely
  so the artifact and the decision cannot drift.
- **AC-8:** WHEN the target range is changed, THE change SHALL be a visible edit to a named
  constant carrying the owner and the date, as `MIN_HOOK_SCORE` does (D-253).
