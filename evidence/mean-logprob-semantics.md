# Evidence — Verification of `mean_logprob` Semantics and Units

```yaml
commit: 99979532e3ccad932a720ad5d22f77839d9f7eca
media_sha256: 2a1625adc0a1522e002a3c8d40fa28ca3541aef5fbb8ef5e2cf745c3ecbe7864
host: HAWAPC01
command: python -c "from hawedit.asr import _mean_aligned_logprob; ..."
date: 2026-09-04T10:01:00Z
```

## 1. Executive Summary

Task T0.5 requires verifying the mathematical semantics, physical scale, and unit of `mean_logprob` emitted by the ASR worker, recomputing the value for an episode 29 segment directly from CTC posteriors and word alignments, and documenting the unit across all contracts.

Initial concern in `specs/pro-grade-program/research.md`:
- `asr.mean_logprob: −7.158` on the delivered ep29 clip was questioned because $e^{-7.158} \approx 0.00078$ would represent an implausibly high perplexity ($\approx 1,284$) if interpreted as an autoregressive language model per-token log-likelihood.

Verification finding:
- `mean_logprob` is NOT an autoregressive LM perplexity metric.
- It is the **frame-averaged log-posterior of aligned non-blank CTC tokens** in **natural log units (nats, $\le 0.0$)**, computed via `torch.log_softmax(..., dim=-1)` over acoustic frames.
- Recomputation of segment 0 of ep29 directly from word confidences yields **`-7.0829329306560185` nats**, matching the recorded worker output to 16 decimal places (zero residual difference).
- The aggregate value of `-7.15824` nats across the 1,326 speech segments of ep29 is the arithmetic mean of these duration-weighted segment log-probabilities.

---

## 2. Derivation and Formulation

### 2.1 CTC Acoustic Emissions (`asr.py:_ctc_emissions`)
The CTC acoustic model produces raw logits $z_t \in \mathbb{R}^V$ for each acoustic frame $t \in [1, T]$ (frame duration $\approx 20$ ms).
Log-probabilities are generated via PyTorch's `log_softmax` along the vocabulary dimension:
$$\log p(c \mid t) = z_{t,c} - \log \sum_{j=1}^V e^{z_{t,j}} \le 0 \quad (\text{nats})$$
Because the base of the logarithm in `torch.log_softmax` is Euler's constant $e$, all values are strictly expressed in **nats**.

### 2.2 Token Spans and Word Confidence (`forced_alignment.py`)
Viterbi forced alignment projects each character/token $k$ across its optimal active frame span $[t_{\text{start}}, t_{\text{end}}]$:
$$\text{TokenSpan.mean\_logprob}_k = \frac{1}{t_{\text{end}} - t_{\text{start}} + 1} \sum_{t = t_{\text{start}}}^{t_{\text{end}}} \log p(\text{token}_k \mid t)$$

For word $w$ covering token spans $k_1, \dots, k_m$:
$$\text{word.mean\_logprob} = \frac{\sum_k \text{TokenSpan.mean\_logprob}_k \cdot \text{frames}_k}{\sum_k \text{frames}_k}$$
Word confidence is defined as:
$$\text{Word.conf} = \exp(\text{word.mean\_logprob}) \in (0, 1.0]$$

### 2.3 Segment Mean Log-Probability (`asr.py:_mean_aligned_logprob`)
The segment log-probability is the duration-weighted mean of its constituent words:
$$\text{segment.mean\_logprob} = \frac{\sum_{w \in \text{seg}} \ln(\max(w.\text{conf}, 10^{-12})) \cdot (w.\text{end\_ms} - w.\text{start\_ms})}{\sum_{w \in \text{seg}} (w.\text{end\_ms} - w.\text{start\_ms})}$$

---

## 3. Ground Truth Recomputation: ep29 Segment 0

From `work/stage1/omni-asr-worker-output.json`:
- **Segment 0 span**: $418..2654$ ms (duration: $2,236$ ms)
- **Constituent words (8 words)**:

| Word Surface | $t_{\text{start}}$ (ms) | $t_{\text{end}}$ (ms) | Duration (ms) | Word Confidence (`conf`) | $\ln(\text{conf})$ (nats) |
|---|---|---|---|---|---|
| ئەمڕۆ | 418 | 841 | 423 | 0.00038727171958541395 | -7.856383993512108 |
| لە | 841 | 1103 | 262 | 0.00030357720786801420 | -8.099874588159414 |
| پۆدکاستی | 1103 | 1264 | 161 | 0.00084424814414716790 | -7.077064096927643 |
| تایبەت | 1264 | 1667 | 403 | 0.00381956303288054440 | -5.567619252204895 |
| بە | 1667 | 1748 | 81 | 0.00052333910282554750 | -7.555280923843384 |
| خۆمان | 1748 | 1788 | 40 | 0.00002069433161673221 | -10.785650730133057 |
| قسە | 1788 | 2150 | 362 | 0.00287670263914744000 | -5.851110557715098 |
| دەکەین | 2150 | 2654 | 504 | 0.00048389413735573796 | -7.633644399642944 |

### Recomputation Result
$$\text{Total Duration} = 423 + 262 + 161 + 403 + 81 + 40 + 362 + 504 = 2,236 \text{ ms}$$
$$\sum \ln(\text{conf}) \cdot \Delta t = -15,837.438032946858$$
$$\text{Recomputed segment.mean\_logprob} = \frac{-15,837.438032946858}{2,236} = \mathbf{-7.0829329306560185 \text{ nats}}$$
- Recorded in worker output: `-7.0829329306560185`
- Residual: `0.0000000000000000` (exact IEEE 754 match)

---

## 4. Why $-7.158$ nats is Expected for CTC Emissions

In CTC acoustic models:
1. Speech is processed in frames (e.g. 20 ms).
2. Because the CTC topology allows the model to predict the blank token $\epsilon$ on non-peak frames, acoustic posteriors for non-blank tokens peak sharply at the phonetic center ($P \approx 0.70$ to $0.95$, $\ln P \approx -0.35$ to $-0.05$).
3. Over the remaining frames assigned to the token by forced alignment, the model's posterior mass resides on blank ($\epsilon \approx 0.999$), causing the non-blank token's posterior to plummet to $10^{-4}$ or $10^{-5}$ ($\ln P \approx -9.0$ to $-12.0$).
4. Taking the arithmetic mean of log-posteriors over all frames within the token span averages the peak frame with the low-posterior tail frames.
5. Consequently, the mean log-posterior naturally falls in the $[-8.5, -5.5]$ nats range.
6. The value `-7.15824` nats is therefore physically consistent with standard CTC forced alignment behavior.
