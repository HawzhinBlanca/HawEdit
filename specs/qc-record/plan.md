# Plan — Human Review is a Record, Not a Flag (`specs/qc-record`)

Approved-by: Hawa

## 1. Objective
Implement Phase 1 Task T1.3 from `specs/pro-grade-program/tasks.md`:
Replace the unauthenticated boolean flag `--qc-pass` with a cryptographically bound `--qc-record <json>` review record. Bind `reviewed_by`, `reviewed_at`, and `reviewed_sha256` into the contract `Qc` block, verify in the Level C Reconciliation Gate, and guarantee that the agent tool surface cannot forge or write one.

## 2. Architecture & Implementation Steps

### Task 1: Core Contract Invariants (`src/hawedit/clip.py`)
- Define `QcRecord` dataclass with fields:
  - `reviewer: str` (non-empty)
  - `reviewed_at: str` (ISO-8601 UTC)
  - `mp4_sha256: str` (64-char hex)
  - `seconds_watched: float` (> 0)
  - `verdict: str` ("pass", "approved")
  - `notes: str = ""`
- Add `QcRecord.from_dict` and `QcRecord.from_json` with strict validation.
- Extend `Qc`:
  - Add fields `reviewed_by: str | None = None`, `reviewed_at: str | None = None`, `reviewed_sha256: str | None = None`.
  - In `__post_init__`: enforce that if `human_reviewed is True`, `reviewed_by`, `reviewed_at`, and `reviewed_sha256` must all be populated and valid.
  - Update `to_dict` and `from_dict`.
- Test: `test_no_code_path_sets_human_reviewed_without_a_matching_record`.

### Task 2: Policy Gate Isolation (`src/hawedit/policy.py`)
- Add `"qc_record"` and `"review_record"` to `_FORBIDDEN_NAME_FRAGMENTS`.
- Test: `test_the_agent_surface_cannot_write_a_review_record`.

### Task 3: Reconciliation Gate Binding (`src/hawedit/delivery.py`)
- In `reconcile_delivery()`: add Clause 8:
  - If `clip.qc and clip.qc.human_reviewed`:
    - Check `clip.qc.reviewed_sha256 == measurement.file.sha256`.
    - If mismatch, raise `DeliveryRefused("qc_sha256_mismatch", expected=measurement.file.sha256, measured=clip.qc.reviewed_sha256)`.
- Test: `test_delivery_refuses_qc_sha256_mismatch`.

### Task 4: CLI Flag Replacement (`src/hawedit/pipeline.py`)
- In `build_parser()`:
  - Remove `--qc-pass`.
  - Add `--qc-record` accepting a path to a JSON file or an inline JSON string.
- In `main()`:
  - Parse `--qc-record` using `QcRecord.from_json()`, construct validated `Qc`, and pass to `run_pipeline()`.
- Test: `test_cli_qc_record_validates_and_binds_to_clip`.

### Task 5: Interactive Revisions Binding (`src/hawedit/proposals.py`)
- In `commit_boundary_revision` and `commit_caption_revision`:
  - After rendering revision MP4, compute its SHA-256 digest.
  - Construct `Qc(auto_pass=False, flags=(), human_reviewed=True, reviewed_by=approver, reviewed_at=datetime.now(UTC).isoformat(), reviewed_sha256=sha256)`.
- Test: `test_revision_qc_binds_approver_and_rendered_sha256`.

## 3. Verification Plan
1. Run unit tests for `clip.py`, `delivery.py`, `policy.py`, `pipeline.py`, `proposals.py`.
2. Run `& "C:\Program Files\Git\bin\bash.exe" scripts/verify.sh` to confirm full 3,350+ test gate pass.
3. Update ledger rows with `scripts/update-ledger.sh`.
