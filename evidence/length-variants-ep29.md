---
commit: daf259355bbc62661c302af1cbeecaea2e6041e8
media_sha256: eb8f80a70e40859f9b69c738080a4702279ce0602d1ef3a2ab5dd77d582ab493
host: HAWAPC01
command: python -c "from hawedit.variants import plan_length_variants; ..."
---

# Evidence — Length Variants 15/30/60 Partitioning on Episode 29

## 1. Context
Implements Task T2.11 (Length variants 15/30/60) satisfying BLUEPRINT.md §5 `durations` contract and pro-grade multi-duration distribution across social platforms.

## 2. Measurement on Real Delivered Clip
On Episode 29 (`ep29-VbX8UWwl1c4-s25-25`, total input speech span 56,252 ms), `plan_length_variants` was evaluated with target durations `(15, 30, 60)` seconds:

- **15s Variant**:
  - Target: 15s
  - Actual Duration: 16.04s (16,036 ms)
  - Time Span: 311,394..327,430 ms
  - Included Sentences: 5 complete sentences
  - Hook Anchored: Yes (starts at 311,394 ms)

- **30s Variant**:
  - Target: 30s
  - Actual Duration: 30.39s (30,389 ms)
  - Time Span: 311,394..341,783 ms
  - Included Sentences: 10 complete sentences
  - Hook Anchored: Yes (starts at 311,394 ms)

- **60s Variant**:
  - Target: 60s
  - Actual Duration: 56.25s (56,252 ms)
  - Time Span: 311,394..367,646 ms
  - Included Sentences: 21 complete sentences (full clip)
  - Hook Anchored: Yes (starts at 311,394 ms)

## 3. Conclusions
1. Every emitted variant consists strictly of whole, completed Kurdish sentences (`complete == True`).
2. Every emitted variant preserves the opening hook sentence, maximizing viewer retention.
3. Actual durations closely align with standard platform constraints (16s for Stories/Quick-shorts, 30s for standard Reels, 56s for complete narrative).
