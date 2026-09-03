# Research: Hook Taxonomy, Payoff and Loop Scoring (Task T4.4)

## 1. Context & Motivation
Task T4.4 in `specs/pro-grade-program/tasks.md` states:
"Verdict gains `hook_type ∈ {question, claim, contrast, story_open, confession}`, `payoff_strength`, `ends_on_a_beat`; keep `reason_ckb`. Used as tiebreakers only until labels exist."
Currently:
- `JudgeVerdict` contains `hook_score`, `self_contained`, `payoff_at_ms`, `meaning_fidelity`, `misleading_edit_risk`, `cultural_landing`, `narrative_role`, `title_ckb`, `description_ckb`, `hashtags_ckb`, `judge`, `clip_in_ms`, `clip_out_ms`, `sv6d`.
- `payoff_at_ms` is validated to fall inside the clip, but never used as an editorial indicator of payoff quality.
- The judge reason (`reason_ckb`) was omitted or discarded.
- In competitive social reel selection, candidates often share similar hook scores; tiebreaking without insight into the hook mechanism or payoff intensity leads to arbitrary choice.

## 2. Taxonomy Definitions
- `hook_type`:
  - `question`: Opens with a provocative or curiosity-inducing question.
  - `claim`: Opens with a bold, controversial, or surprising factual claim.
  - `contrast`: Opens with an unexpected juxtaposition ("They thought X, but actually Y").
  - `story_open`: Opens with an anecdote or narrative premise.
  - `confession`: Opens with a personal vulnerability, admission, or insider revelation.
- `payoff_strength`: Float in [0.0, 1.0] measuring whether the promise of the hook is delivered upon with clarity, punch, or insight.
- `ends_on_a_beat`: Boolean indicating if the final cadence lands naturally on an emphatic pause or loop-friendly closure rather than trailing off mid-thought.
- `reason_ckb`: Central Kurdish textual justification explaining the judge's verdict rationale.

## 3. Backward Compatibility
- To avoid breaking existing serialized JSON contracts and fixtures, new fields on `JudgeVerdict` have safe defaults (`hook_type="claim"`, `payoff_strength=0.5`, `ends_on_a_beat=True`, `reason_ckb="کورتەی پەسەندکردن."`).
- In `Editorial` (`src/hawedit/clip.py`), these fields are optional (`None` by default) so existing serialized `Clip` JSON documents remain fully deserializable (satisfying D-033 / Level C frozen contract principles).
- In `pipeline.py`, tiebreaking on shippable candidates incorporates `(verdict.hook_score, verdict.payoff_strength, verdict.ends_on_a_beat)`.
