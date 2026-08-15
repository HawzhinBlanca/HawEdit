# Tasks — speaker-boundary-fusion

- [x] T1 Strict injected diarization producer and artifact validation
- [x] T2 Structured pipeline stage, honest completeness, and Stage 5 turn fusion
- [ ] T3 Exact-path commit, hosted CI, and evidence-backed promotion

## Definition of Done

- Every EARS criterion in `spec.md` is mapped to a named test.
- The exact canonical `bash scripts/verify.sh` gate passes from committed source.
- Rows are flipped only by `scripts/update-ledger.sh` against that gate's JUnit evidence.
- Required hosted checks pass at the exact pushed SHA.
- No production pyannote, DER, active-speaker crop, or AC-9 completion claim is made without the
  gated model bytes and labelled multi-speaker evidence.
