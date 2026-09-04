# Impact Map — `mean_logprob` Semantics (`specs/mean-logprob-semantics`)

## Symbols Touched

1. `hawedit.transcripts.AsrProvenance`:
   - Clarify in docstring that `mean_logprob` is in natural logarithm units (nats, $\le 0.0$), representing the mean of segment log-probabilities derived from frame-level CTC posteriors.
   - Callers affected: None (documentation clarification).

2. `hawedit.transcripts.SegmentConfidence`:
   - Clarify in docstring that `mean_logprob` is in nats ($\le 0.0$).
   - Callers affected: None (documentation clarification).

3. `hawedit.clip.Clip.to_dict`:
   - Clarify in docstring that `asr.mean_logprob` in the serialized contract is in nats ($\le 0.0$).
   - Callers affected: None (documentation clarification).

4. `hawedit.asr._mean_aligned_logprob`:
   - Clarify docstring explaining that word confidences ($e^{\text{mean\_logprob}}$) are mapped back to nats via `math.log` and duration-weighted.

5. `tests/test_transcripts.py`:
   - Add `test_mean_logprob_is_a_per_token_mean_in_nats` validating:
     * Natural log base ($e$), nats unit semantics $\le 0.0$.
     * Monotonic relationship $\text{conf} = \exp(\text{mean\_logprob}) \in (0, 1.0]$.
     * Recomputation invariance: segment `mean_logprob` is duration-weighted average of word logprobs in nats.
     * Recomputation check against the real ep29 segment 0 values.

6. `evidence/mean-logprob-semantics.md`:
   - New evidence file binding the commit, media SHA-256, and recomputed math on ep29 segment 0.
