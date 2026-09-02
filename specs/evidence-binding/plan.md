# Plan — Evidence Binding (`specs/evidence-binding`)

Approved-by: Hawa

## 1. Objective
Implement Phase 1 Task T1.5 from `specs/pro-grade-program/tasks.md`:
Every `evidence/*.md` created after 2026-09-02 must carry `commit:`, `media_sha256:` (or `n/a: no media`), `host:`, `command:` in a header block; `test_claims` refuses otherwise and checks the commit exists in history. Existing files untouched.

## 2. Implementation Steps

### Task 1: Contract Enforcement in `tests/test_claims.py`
- Add `test_new_evidence_names_its_commit_media_and_host()` in `tests/test_claims.py`.
- Query all evidence files in `evidence/`.
- Determine introduction date using `git log --diff-filter=A --name-only --format=COMMIT:%cI -- evidence/`.
- For any file introduced after `2026-09-02T23:59:59+03:00` or untracked/uncommitted:
  - Extract the YAML header from lines between ````yaml` / ```` or `---` / `---`.
  - Validate `commit`: must be 40-character or 64-character hex, and must resolve in `git cat-file -e <commit>^{commit}`.
  - Validate `media_sha256`: must be 64-character lowercase hex OR start with `n/a`.
  - Validate `host`: must be non-empty string.
  - Validate `command`: must be non-empty string.
- Add unit test asserting refusal on missing header, invalid commit SHA, invalid media SHA, missing host/command.

## 3. Verification Plan
- Run `verify.sh --fast` (lint and typecheck).
- Run the full verification gate via `scripts/update-ledger.sh evidence-binding T1 test_new_evidence_names_its_commit_media_and_host`.
