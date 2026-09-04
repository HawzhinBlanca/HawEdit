# Plan — Comparison Kit for Blind Pairwise Study (Task T5.1)

Research: `specs/comparison-kit/research.md`
Specification: `specs/comparison-kit/spec.md`
Impact Map: `specs/comparison-kit/impact-map.md`

Approved-by: Hawa — inherited from the approved autonomy-first execution plan, 2026-08-17

## Architecture & Design

### 1. Data Structures (`src/hawedit/comparison_kit.py`)
- `PairCandidate`: Dataclass representing one comparison item: `pair_id`, `system_path`, `human_path`, `topic_ckb`, `duration_s`.
- `BlindedItem`: Dataclass containing `pair_id`, `blinded_path_a`, `blinded_path_b`, `sha256_a`, `sha256_b`.
- `BlindedStudy`: Dataclass containing `study_id`, `items: tuple[BlindedItem, ...]`, `unblinding_map: dict[str, dict[str, str]]`, `seed: int | str`.
- `RatingDimension`: Enums / dataclasses for Kurdish rating scores (Hook 1-5, Clarity 1-5, Shareability 1-5, Misleading bool, Preference 'A'/'B'/'tie').
- `PairRating`: Dataclass representing one rater's evaluation of one pair.
- `RaterSubmission`: Dataclass representing one reviewer's full set of ratings.
- `StudyMetrics`: Statistical summary dataclass containing:
  - `total_comparisons: int`
  - `system_wins: int`
  - `human_wins: int`
  - `ties: int`
  - `system_win_rate: float`
  - `ci_lower: float` (Wilson score 95%)
  - `ci_upper: float` (Wilson score 95%)
  - `better_than_a_team: bool` ($ci_{lower} > 0.50$)
  - `hook_mean_diff: float` (system - human)
  - `clarity_mean_diff: float` (system - human)
  - `shareability_mean_diff: float` (system - human)
  - `misleading_rate_system: float`
  - `misleading_rate_human: float`

### 2. Core Functions
- `wilson_score_interval(p_hat: float, n: int, confidence: float = 0.95) -> tuple[float, float]`
- `prepare_blind_study(pairs: Sequence[PairCandidate], output_dir: Path, seed: int = 42) -> BlindedStudy`
- `generate_kurdish_rating_form(study: BlindedStudy) -> dict[str, Any]` (and formatted markdown text)
- `validate_ratings(ratings_payload: dict[str, Any], expected_pair_ids: set[str]) -> RaterSubmission`
- `analyze_study(submissions: Sequence[RaterSubmission], unblinding_map: dict[str, dict[str, str]]) -> StudyMetrics`
- `export_to_qc_records(submission: RaterSubmission, study: BlindedStudy) -> tuple[QcRecord, ...]`

### 3. Verification Plan
- Unit tests in `tests/test_comparison_kit.py`:
  - Deterministic randomisation & blinding: verify seed reproduces identical A/B assignments and different seeds produce different assignments.
  - Wilson score interval math: test known analytical cases (e.g. $p=0.5, n=100$; $p=1.0$; $p=0.0$; edge cases $n=1$).
  - Criterion `better_than_a_team`: test synthetic scenarios where lower bound > 0.50 vs lower bound <= 0.50.
  - Kurdish Sorani rating form validity and UTF-8 roundtrip.
  - Input validation: reject invalid scores, empty reviewers, mismatched pair IDs.
  - Full end-to-end flow with synthetic raters generating `StudyMetrics` and `QcRecord` exports.
