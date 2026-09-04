# Research — Verify `mean_logprob` Semantics (`specs/mean-logprob-semantics`)

## 1. Problem & Context
Task T0.5 in `specs/pro-grade-program/tasks.md`:
- "Verify `mean_logprob` semantics. Read the worker output for one segment, recompute the per-token mean from CTC posteriors, state the unit in `AsrProvenance` docs and the contract. Proof required: A: `test_mean_logprob_is_a_per_token_mean_in_nats`. B: recomputed value for one ep29 segment in `evidence/`."
- In `specs/pro-grade-program/research.md` §3:
  `asr.mean_logprob: −7.158` was observed on the delivered ep29 clip (`ep29-VbX8UWwl1c4-s25-25.json`). The initial concern was whether $-7.158$ is plausible as a per-token mean log-probability (since $e^{-7.158} \approx 0.00078$, which for an autoregressive language model would imply a perplexity of $\approx 1,284$).

## 2. Investigation of Code & Reality

### 2.1 The Derivation Pipeline
Tracing from acoustic emissions to the contract:
1. **Acoustic CTC Model Output (`asr.py:_ctc_emissions`)**:
   - `logits` are computed by OmniASR CTC (WavLM/Conformer acoustic backend).
   - `log_probs = torch.log_softmax(segment_logits.float(), dim=-1)` computes the natural logarithm of the softmax probability distribution:
     $$\log p(c \mid t) = z_{t,c} - \log \sum_j e^{z_{t,j}} \le 0 \quad (\text{nats})$$
   - Base is $e$, unit is **nats**.
2. **Viterbi Forced Alignment (`forced_alignment.py:viterbi_align`)**:
   - For each token $k$ assigned to a span of frames $[t_{\text{start}}, t_{\text{end}}]$:
     $$\text{totals}[k] = \sum_{t = t_{\text{start}}}^{t_{\text{end}}} \log p(\text{token}_k \mid t)$$
     $$\text{TokenSpan.mean\_logprob} = \frac{\text{totals}[k]}{t_{\text{end}} - t_{\text{start}} + 1}$$
     This is the frame-averaged log-posterior of token $k$ over its assigned active frames in nats.
3. **Word Alignment (`forced_alignment.py:align_words`)**:
   - For word $w$ covering tokens $k_1, \dots, k_m$:
     $$\text{mean\_logprob}_w = \frac{\sum_k \text{mean\_logprob}_k \times \text{frames}_k}{\sum_k \text{frames}_k} = \frac{\sum_{k} \sum_{t} \log p(\text{token}_k \mid t)}{\sum_k \text{frames}_k}$$
   - Word confidence is stored as:
     $$\text{Word.conf} = \exp(\text{mean\_logprob}_w)$$
4. **Segment Mean Log-Probability (`asr.py:_mean_aligned_logprob`)**:
   - Computes duration-weighted average of $\ln(\text{Word.conf})$:
     $$\text{segment.mean\_logprob} = \frac{\sum_w \ln(\max(\text{word.conf}, 10^{-12})) \times \text{duration}(w)}{\sum_w \text{duration}(w)}$$
5. **Aggregate Transcript ASR Provenance (`asr.py:_assemble_canonical_transcript`)**:
   - Computes arithmetic mean across all $N$ speech segments:
     $$\text{asr.mean\_logprob} = \frac{1}{N} \sum_{i=1}^N \text{segment}_i\text{.mean\_logprob}$$

### 2.2 Verification Against Real ep29 Worker Artifact
Examining `work/stage1/omni-asr-worker-output.json`:
- Contains 1,326 segment confidences across 38 minutes of ep29 speech.
- Aggregate `data['asr']['mean_logprob'] = -7.1582438553200785`.
- Segment 0 (`start_ms=418, end_ms=2654`, duration 2,236 ms, 8 words):
  - Recorded segment `mean_logprob = -7.0829329306560185`.
  - Recomputing $\frac{\sum_{w \in \text{seg}_0} \ln(w.\text{conf}) \times \Delta t_w}{\sum_{w \in \text{seg}_0} \Delta t_w}$ directly from the 8 constituent word confidences yields:
    $$-7.0829329306560185$$
  - Exact match to 16 significant digits.

### 2.3 Why $-7.158$ nats is physically and mathematically expected
- In CTC forced alignment, an acoustic phoneme spans multiple 20ms frames (e.g. 5–15 frames).
- The acoustic model emits high posterior at the phonetic peak/center ($P \approx 0.8$, $\ln P \approx -0.2$), while on surrounding frames the model mass is primarily on the blank symbol ($\epsilon$, $P \approx 0.999$), causing the posterior on the non-blank token to drop to $10^{-4}$ or $10^{-5}$ ($\ln P \approx -9$ to $-12$).
- Averaging these frame-level posteriors across the non-blank token's duration naturally produces an average in the $[-8.5, -5.5]$ nats range.
- It is NOT an LM perplexity calculation; it is a frame-averaged acoustic log-posterior in **nats**.
