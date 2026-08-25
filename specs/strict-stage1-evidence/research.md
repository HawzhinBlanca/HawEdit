# Strict Stage 1 evidence — research

## Authority

- `BLUEPRINT.md` §3 Stage 1 requires the bottom confidence quartile and material LLM/CTC
  disagreement to control validator routing.
- Kurdish invariant #5 makes CTC-derived timing and confidence evidence authoritative; malformed
  numeric evidence must not be interpreted as a real timestamp or score.

## Reproduced current behaviour

On 2026-08-17 at `f8678681aa22998a9c1d821486d2f3daae17c906`:

- `UnalignedSpeech(False, True, "x")` was accepted as a 0..1 ms speech gap.
- `SegmentConfidence(False, True, float("nan"))` was accepted.
- `AsrProvenance(..., mean_logprob=True | NaN | Infinity | "-1")` was accepted.
- `RawTranscript.from_json` used permissive `json.loads`, so Python's non-standard `NaN` token
  and duplicate JSON keys were not refused at the canonical artifact boundary.
- `pipeline.run_pipeline` feeds supplied transcript confidence through
  `scores_from_transcript` and `select_for_validation`; a malformed persisted value therefore
  reaches the §3 routing sort and report rather than remaining a parser-only issue.

The constructors check positive duration and positive log-probabilities, but Python booleans are
integers and comparisons with NaN are false. Type annotations do not provide runtime validation.

## Existing correct boundaries

- `Word` already rejects boolean timestamps, non-finite confidence and multiline surface forms.
- `asr.SegmentTranscript` already requires a finite log-probability `<= 0`.
- `asr._failure_reason` already emits a printable one-line reason capped at 1,024 characters.
- The CLI already converts `ValueError` and `TypeError` into a traceback-free exit 2.

## Chosen bounded unit

Make persisted Stage 1 evidence at least as strict as the live producer evidence:

1. exact non-boolean integer media-clock bounds;
2. finite, non-boolean numeric log-probabilities `<= 0`;
3. bounded printable one-line failure reasons;
4. strict JSON object/array/member shapes, duplicate-key refusal and non-standard numeric refusal;
5. the same numeric contract at the downstream `SegmentScore` boundary.

This does not choose any blocked threshold, change ASR words, change model routing policy, or
claim real-corpus accuracy.
