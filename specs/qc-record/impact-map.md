# Impact Map — Human Review Record (`specs/qc-record`)

## 1. Modified Symbols & Files

| Component | File | Symbol | Nature of Change |
|---|---|---|---|
| Core Contract | `src/hawedit/clip.py` | `class Qc` | Add `reviewed_by`, `reviewed_at`, `reviewed_sha256` with validation |
| Core Contract | `src/hawedit/clip.py` | `class QcRecord` | New dataclass for review records with JSON parsing |
| Pipeline CLI | `src/hawedit/pipeline.py` | `build_parser()` | Remove `--qc-pass`, add `--qc-record` |
| Pipeline Runtime | `src/hawedit/pipeline.py` | `main()` / `run_pipeline()` | Ingest `QcRecord`, wire into `Qc` |
| Delivery Gate | `src/hawedit/delivery.py` | `reconcile_delivery()` | Add Clause 8 reconciling `reviewed_sha256` against `measurement.file.sha256` |
| Editorial Revisions | `src/hawedit/proposals.py` | `commit_boundary_revision`, `commit_caption_revision` | Bind interactive human approver name, timestamp, and render SHA-256 to `Qc` |
| Policy Gate | `src/hawedit/policy.py` | `_FORBIDDEN_NAME_FRAGMENTS` | Assert review record generation is blocked from agents |

## 2. Affected Callers & Test Surface

- **Tests verifying `Qc` structure**:
  - `tests/test_clip.py`: Update callers to test new fields and validation invariants.
- **Tests verifying delivery reconciliation**:
  - `tests/test_delivery.py`: Add test verifying `DeliveryRefused("qc_sha256_mismatch")`.
- **Tests verifying pipeline CLI**:
  - `tests/test_pipeline.py`: Migrate `--qc-pass` assertions to `--qc-record`.
- **Policy Gate Tests**:
  - `tests/test_policy.py`: Add `test_the_agent_surface_cannot_write_a_review_record`.
