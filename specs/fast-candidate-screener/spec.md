# Specification — Fast Candidate Screener Funnel

## Acceptance Criteria

- **AC-1:** WHEN candidate spans are generated from Stage 3 and `--screener` is enabled, THE pipeline SHALL evaluate candidate spans via a `CandidateScreener` before invoking Stage 4 `EditorialJudge`.
- **AC-2:** WHEN `GeminiFlashScreener` is used, THE screener SHALL score candidate spans on hook potential, payoff strength, self-containment, and misleading risk using structured outputs without text hallucination.
- **AC-3:** WHEN `JevScreener` is selected, THE screener SHALL query TypeSafe System One using `Choice`, `Score`, and `Noul` primitives, mapping calibrated decisions to `ScreenedCandidate`.
- **AC-4:** WHEN `JevScreener` is selected but `TYPESAFE_API_KEY` is not present, THE system SHALL raise a strict fail-stop `CredentialError` explaining the missing requirement, rather than silently falling back.
- **AC-5:** WHEN candidates are screened, THE pipeline SHALL rank them by calibrated composite score and dispatch only the top survivor(s) to `EditorialJudge` for full Sorani Kurdish metadata generation.
- **AC-6:** WHEN `--screener none` (or default without screener flag) is specified, THE pipeline SHALL preserve existing behavior and pass candidates directly to `EditorialJudge`.
