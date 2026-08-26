# Specification — judge the top N candidates

## Acceptance criteria

- **AC-1:** WHEN Stage 3 returns candidates and a judge is configured, THE pipeline SHALL judge
  up to N of them in `_candidate_priority` order rather than exactly one.
- **AC-2:** WHEN a candidate yields no complete contiguous sentence run, THE pipeline SHALL skip
  it without spending a billed call on it.
- **AC-3:** WHEN more than one judged candidate clears §2's editorial thresholds, THE pipeline
  SHALL ship the one with the highest `hook_score`.
- **AC-4:** WHEN no judged candidate clears the thresholds, THE pipeline SHALL refuse and SHALL
  name every candidate's scores, so the operator sees what was rejected and why.
- **AC-5:** WHEN a verdict is obtained, THE pipeline SHALL persist it before deciding whether to
  render, so a refused run does not discard a billed model call.
- **AC-6:** WHEN N is 1, THE behaviour SHALL be identical to today's.
- **AC-7:** WHEN artifacts already exist for a candidate's selection, THE pipeline SHALL refuse
  that candidate before its billed call, preserving today's ordering.
- **AC-8:** WHEN candidates are judged and rejected, THE run record SHALL distinguish "not
  eligible" from "judged and below threshold" — §5 calls the rejection set the only measure of
  recall, and the two are different measurements.
