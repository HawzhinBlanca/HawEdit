# Plan — Fast Candidate Screener Funnel (Gemini Flash & TypeSafe Jev)

## Summary
Implements a pluggable Two-Tier Candidate Screening Funnel. In full-length episodes with dozens of candidate spans, screening prunes candidates in sub-second time using cheap/fast System One decision models (`GeminiFlashScreener` or `JevScreener`), passing only top survivor(s) to Gemini 2.5 Pro for full Sorani Kurdish editorial copywriting.

## Tasks

- [ ] **TASK-1**: Define `ScreenedCandidate` and `CandidateScreener` interface in `src/hawedit/screener.py` with composite ranking formula.
- [ ] **TASK-2**: Implement `GeminiFlashScreener` using structured JSON schema over Gemini 2.5 Flash / Flash-Lite.
- [ ] **TASK-3**: Implement `JevScreener` with TypeSafe System One HTTP protocol (`Choice`, `Score`, `Noul`) and strict credential validation.
- [ ] **TASK-4**: Integrate `--screener` flag into `hawedit.pipeline` and Stage 4 loop.
- [ ] **TASK-5**: Add `TYPESAFE_API_KEY` credential support in `hawedit.credentials`.
- [ ] **TASK-6**: Comprehensive test suite in `tests/test_screener.py` covering all acceptance criteria AC-1 to AC-6.
- [ ] **TASK-7**: Record ADR `D-111` in `DECISIONS.md`.

## Approvals
Approved-by: Human Operator
