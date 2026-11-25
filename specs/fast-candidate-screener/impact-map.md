# Impact Map — Fast Candidate Screener Funnel

## Affected Files and Symbols

### 1. `src/hawedit/screener.py` [NEW]
- `ScreenedCandidate`: Data class representing a screened candidate with calibrated scores.
- `CandidateScreener`: Protocol defining `.screen(candidates, top_k) -> Sequence[ScreenedCandidate]`.
- `GeminiFlashScreener`: Screener implementation using Gemini 2.5 Flash / Flash-Lite.
- `JevScreener`: Screener implementation for TypeSafe Jev API.
- `get_screener(name, client=None) -> CandidateScreener | None`: Factory function.

### 2. `src/hawedit/pipeline.py` [MODIFY]
- Affected caller: `_automatic_sentence_selection` or Stage 3/4 candidate loop.
- Argument parser: add `--screener` choice (`none`, `gemini-flash`, `jev`, default `none`).
- In Stage 4 execution: when `--screener` is active and multiple candidates exist, screen candidates prior to `judge.judge(...)`.

### 3. `src/hawedit/credentials.py` [MODIFY]
- Symbol: `TYPESAFE_API_KEY = "TYPESAFE_API_KEY"`
- Add validator / masking for `TYPESAFE_API_KEY`.

### 4. `DECISIONS.md` [MODIFY]
- Record ADR `D-111: Two-Tier Candidate Screening Funnel with Optional TypeSafe Jev Accelerator`.

### 5. `tests/test_screener.py` [NEW]
- Unit tests covering AC-1 through AC-6.
