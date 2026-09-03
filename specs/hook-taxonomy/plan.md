# Implementation Plan: Hook Taxonomy, Payoff, and Loop Scoring (Task T4.4)

## Proposed Changes

### Task T1: Core Data Models in `src/hawedit/judge.py` and `src/hawedit/clip.py`
- Define `HOOK_TYPES = frozenset({"question", "claim", "contrast", "story_open", "confession"})` in `src/hawedit/judge.py` and export it.
- Update `JudgeVerdict` in `src/hawedit/judge.py`:
  Add `hook_type: str = "claim"`, `payoff_strength: float = 0.5`, `ends_on_a_beat: bool = True`, `reason_ckb: str = "کورتەی پەسەندکردن."`.
  Validate `hook_type in HOOK_TYPES`, `0.0 <= payoff_strength <= 1.0`, `ends_on_a_beat is bool`, and `reason_ckb` via `_kurdish_field`.
  Update `to_editorial()`, `to_dict()`, and `from_dict()`.
- Update `Editorial` in `src/hawedit/clip.py`:
  Add optional fields `hook_type`, `payoff_strength`, `ends_on_a_beat`, `reason_ckb`.
  Update `to_dict()` and `from_dict()`.

### Task T2: Gemini Integration and Pipeline Tiebreaking
- Update `VERDICT_SCHEMA` and `_PROMPT` in `src/hawedit/gemini.py` to instruct Gemini on taxonomy and payoff scoring.
- Update `_to_verdict` in `gemini.py` to parse the new fields.
- Update candidate selection tiebreaking in `src/hawedit/pipeline.py` line 2075:
  `winner, winning_run, verdict = max(shippable, key=lambda item: (item[2].hook_score, getattr(item[2], "payoff_strength", 0.0), getattr(item[2], "ends_on_a_beat", False)))`.

### Task T3: Unit Tests, Full Gate, and Ledger
- Add unit tests in `tests/test_judge.py` and `tests/test_clip.py` verifying validation, serialization, and backward compatibility.
- Run `verify.sh --fast` and full `verify.sh`.
- Ratchet floor, update ledger, and flip rows.
