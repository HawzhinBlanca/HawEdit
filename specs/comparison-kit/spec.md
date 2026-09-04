# Specification — Comparison Kit for Blind Pairwise Study (Task T5.1)

## Acceptance Criteria (EARS Format)

### AC-1: Seeded Pair Randomisation and Blinding
WHEN `prepare_blind_study` is called with pairs of video clips (system vs human) and a seed, THE system SHALL assign each pair to Option A and Option B pseudo-randomly, write blinded media copies or symlinks/staged files with sanitized names (`pair_{i:02d}_A.mp4`, `pair_{i:02d}_B.mp4`), and output an unblinding key sealed with SHA-256 digest.

### AC-2: Native Kurdish Sorani Rating Form Generation
WHEN `generate_rating_form` is invoked, THE system SHALL emit a structured evaluation form in Sorani Kurdish (`ckb`) capturing ratings for:
1. Hook strength (1–5)
2. Clarity (1–5)
3. Would share (1–5)
4. Misleading edit (boolean)
5. Preferred option ('A', 'B', 'tie')

### AC-3: Review Submission and Validation
WHEN `load_and_validate_ratings` is called with reviewer ratings, THE system SHALL verify that:
- Reviewer identity is non-empty.
- All pairs in the study are evaluated.
- Numerical scores are integer values in [1, 5].
- Misleading flag is boolean.
- Preferred option is one of 'A', 'B', 'tie'.
- No duplicate submissions from the same reviewer.

### AC-4: Win-Rate and Wilson Score Confidence Interval Analysis
WHEN `analyze_study_results` is called with validated ratings and the unblinding key, THE system SHALL:
- Calculate the system win rate: $p = (\text{wins} + 0.5 \times \text{ties}) / \text{total}$.
- Compute two-sided 95% Wilson score confidence interval $[ci_{lower}, ci_{upper}]$.
- Set `better_than_a_team = True` ONLY IF $ci_{lower} > 0.50$, and `False` otherwise.
- Aggregate per-dimension metrics (hook, clarity, shareability, misleading edit rates).

### AC-5: Integration with T1.3 Reviewer Records
WHEN `export_qc_records` is called, THE system SHALL transform individual ratings into valid `QcRecord` instances with reviewer name, ISO timestamp, clip SHA-256, and verdicts.
