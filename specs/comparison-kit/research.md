# Research — Comparison Kit for Blind Pairwise Study (Task T5.1)

## 1. Problem Context

Task **T5.1** from `specs/pro-grade-program/tasks.md` establishes the evaluation machinery required for **H7**:
> "Blind pairwise comparison: system vs a human editor. Commission one professional Kurdish editor to cut 5 clips from ep29 (same brief: 30–90 s, 9:16, captions). The system cuts 5 in production profile. ≥ 20 Kurdish viewers rate blind pairs (pre-registered form: hook, clarity, would-share, misleading?). Report win-rate with 95 % CI. 'Better than a team' is claimable only if the CI's lower bound exceeds 50 %. Anything else is reported as the number it is. Kit = T5.1."

Without an automated, tamper-evident comparison kit, human comparisons risk:
1. **Experimenter bias & leakage**: File naming, metadata, or presentation revealing whether a clip was AI-generated or human-edited.
2. **Ad-hoc scoring**: Uncalibrated rating rubrics in English rather than native Kurdish Sorani (`ckb`).
3. **Flawed statistical inference**: Naive point-estimate win-rates ignoring sample variance rather than rigorous Wilson score 95% confidence intervals.
4. **Disconnection from QC evidence**: Ratings stored in non-standard spreadsheets rather than the immutable `QcRecord` format established in Task T1.3.

## 2. Requirements Analysis

### 2.1 Randomiser & Blinding
- Input: Pairs of video clips (system-rendered clip and human-edited clip for the same episode/topic).
- Assignment: Deterministic cryptographic PRNG (seeded with study seed or HMAC-SHA256) mapping each pair to Option A and Option B.
- Blinded output: Re-names/copies video files to sanitized identifiers (`pair_{i:02d}_A.mp4`, `pair_{i:02d}_B.mp4`) with identical container attributes and zero metadata leakage.
- Unblinding key: Output JSON mapping `pair_id` -> `{"A": system_or_human, "B": system_or_human}`, sealed with SHA-256 digest until evaluation.

### 2.2 Native Kurdish Sorani Rating Form
- Native Sorani Kurdish rubric covering the 4 core dimensions specified in H7 plus overall choice:
  1. **Hook (0–3s)**: `سەرنجڕاکێشی لە ۳ چرکەی یەکەم` (scale 1–5)
  2. **Clarity**: `ڕوونی پەیام و چیرۆک` (scale 1–5)
  3. **Viral Shareability**: `ئارەزووی بڵاوکردنەوە لە تۆڕە کۆمەڵایەتییەکان` (scale 1–5)
  4. **Misleading Risk**: `چەواشەکاری یان شێواندنی واتا` (boolean: بەڵێ / نەخێر)
  5. **Preference**: `هەڵبژاردنی پەسەندکراو` (Option A / Option B / یەکسان - Tie)

### 2.3 Statistical Analysis & Confidence Intervals
- Calculates win-rate for system vs human editor:
  $$p = \frac{\text{wins} + 0.5 \times \text{ties}}{\text{total}}$$
- Computes two-sided 95% Wilson score confidence interval:
  $$w = \frac{p + \frac{z^2}{2n} \pm z \sqrt{\frac{p(1-p)}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}$$
  with $z = 1.959963984540054$.
- Validates the explicit rule: `"Better than a team"` is only claimable if `ci_lower > 0.50`.
- Aggregates per-dimension metrics (mean score differences, misleading rate).

### 2.4 Integration with Review Records (T1.3)
- Capable of exporting ratings into `QcRecord` structures (`reviewer`, `reviewed_at`, `mp4_sha256`, `seconds_watched`, `verdict`, `notes`).

## 3. Existing Codebase Anchors
- `src/hawedit/clip.py`: `QcRecord` format and serialization.
- `src/hawedit/normalize.py`: Kurdish text handling.
- `src/hawedit/editorial_acceptance.py`: Blinded study principles and packet freezing.
- Zero external dependencies: pure standard library (`dataclasses`, `hashlib`, `json`, `math`, `pathlib`).
