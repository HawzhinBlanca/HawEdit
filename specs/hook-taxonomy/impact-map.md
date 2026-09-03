# Impact Map: Hook Taxonomy, Payoff, and Loop Scoring (Task T4.4)

## 1. Direct Symbols Affected
- `hawedit.judge.HOOK_TYPES`: New constant `frozenset({"question", "claim", "contrast", "story_open", "confession"})`.
- `hawedit.judge.JudgeVerdict`: Add fields `hook_type: str = "claim"`, `payoff_strength: float = 0.5`, `ends_on_a_beat: bool = True`, `reason_ckb: str = "کورتەی پەسەندکردن."`.
- `hawedit.judge.JudgeVerdict.to_editorial()`: Pass new fields to `Editorial`.
- `hawedit.clip.Editorial`: Add optional fields `hook_type: str | None = None`, `payoff_strength: float | None = None`, `ends_on_a_beat: bool | None = None`, `reason_ckb: str | None = None`.
- `hawedit.gemini.VERDICT_SCHEMA`: Update JSON schema to define `hook_type`, `payoff_strength`, `ends_on_a_beat`, `reason_ckb`.
- `hawedit.gemini._to_verdict()`: Parse and pass new fields to `JudgeVerdict`.
- `hawedit.pipeline.run_pipeline`: Tiebreak candidate selection with `(verdict.hook_score, verdict.payoff_strength, verdict.ends_on_a_beat)`.

## 2. Callers & Dependents
- `tests/test_judge.py`: Schema validation, roundtrip tests, and invalid value rejection tests.
- `tests/test_clip.py`: Contract serialization/deserialization tests.
- Existing tests: Backward compatibility ensured by sensible defaults on `JudgeVerdict` and optionality on `Editorial`.
