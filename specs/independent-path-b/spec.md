# Specification — independent-path-b (T4.2)

## EARS Requirements

### AC-1: Independent Path B Execution
WHEN `--visual` (or a `visual_composer`) is enabled and no explicit `--visual-query` or Path A candidate is provided, THE system SHALL execute visual retrieval against `DEFAULT_NONVERBAL_VISUAL_QUERY` ("پێکەنین، کاردانەوە، سەرسوڕمان، جووڵە") and SHALL record `visual_query_source="default:nonverbal"`.

### AC-2: Dual-Path Union & Candidate Attribution
WHEN both Path A and Path B produce candidates, THE system SHALL union them via `merge_candidates` without filtering either path, SHALL attribute each candidate's `discovery_path` as `VERBAL`, `VISUAL`, or `BOTH`, and SHALL record candidates found by Path B only.

### AC-3: Explicit Path A Seeding Mode
WHEN `--visual-seed-path-a` is explicitly requested and no explicit query is provided, THE system SHALL scope retrieval to the words of the rank-1 Path A candidate with `visual_query_source="path_a:<candidate_id>"`, and SHALL refuse with `StageSkipped` if Path A failed or produced no candidates.

### AC-4: CLI Independent Producer Validation
WHEN `--auto-select` is supplied with `--visual` alone (without `--gemini` or `--vertex-project`), THE CLI SHALL accept `--visual` as a valid Stage 3 candidate producer using the canonical non-verbal query set.

### AC-5: Reporting & Recall Breakdown
WHEN Stage 3 completes with merged candidates, THE report and summary output SHALL report candidate counts broken down by discovery path (`by_path`), explicitly noting candidates discovered by Path B only.
