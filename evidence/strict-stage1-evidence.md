# Strict Stage 1 evidence acceptance — 2026-08-17

## Scope

Commit candidate based on `f8678681aa22998a9c1d821486d2f3daae17c906`, Windows CPython
3.12, with no GPU, network, model or credential dependency.

`BLUEPRINT.md` §3 Stage 1 routes the bottom confidence quartile and material LLM/CTC
disagreement to the validator. Persisted timestamps and confidence therefore participate in a
production decision; they are not descriptive metadata.

## Reproduced defects

Before the change, all of these were accepted:

- `UnalignedSpeech(False, True, "x")` as a 0..1 ms media span;
- `SegmentConfidence(False, True, NaN)`;
- aggregate ASR confidence values `true`, `NaN`, `Infinity`, and the string `"-1"`;
- duplicate JSON keys, because `json.loads` silently retained the last value;
- Python's non-standard JSON constants `NaN` and `Infinity`;
- dictionaries in place of evidence arrays, which became silently empty tuples;
- multiline, control-bearing, and unbounded client-facing failure reasons.

The supplied-transcript runner immediately calls `scores_from_transcript` and
`select_for_validation`, so malformed confidence reached the real routing boundary.

## Enforced contract

- media-clock evidence uses exact non-boolean, non-negative integer milliseconds;
- log-probabilities are numeric, non-boolean, finite and `<= 0`;
- failure reasons are non-empty printable single lines capped at the producer's existing 1,024
  character bound;
- raw and normalized transcript parsers reject duplicate keys, non-standard numeric constants,
  non-object top levels, wrong container/member shapes, missing fields and unknown fields;
- the downstream public `SegmentScore` boundary independently enforces the same confidence rule;
- legacy optional transcript fields remain optional and valid HawEdit artifacts round-trip exactly.

## Verification

- 455 focused transcript/escalation/pipeline tests passed.
- 264 adjacent ASR/clip/alignment/index/Path-A/render/review-regression tests passed.
- Ruff check and format passed on every changed source/test file.
- strict mypy passed on both changed source modules.
- `git diff --check` passed.

The first canonical gate reached 2,745 collected tests. Its only failures were intentional
cross-contract signals: release tests refused the dirty checkout and the checked-in WSL VEX
policy refused the new source digest. This file records that state before the explicit-path commit;
the post-commit canonical gate is the acceptance authority.
