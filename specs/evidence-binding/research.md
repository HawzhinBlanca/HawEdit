# Research — Evidence Binding (`specs/evidence-binding`)

> Task T1.5 of `specs/pro-grade-program/tasks.md`:
> "Every `evidence/*.md` created after 2026-09-02 must carry `commit:`, `media_sha256:` (or `n/a: no media`), `host:`, `command:` in a header block; `test_claims` refuses otherwise and checks the commit exists in history. Existing files untouched."
> Proof required: A: `test_new_evidence_names_its_commit_media_and_host`. Decider: —.

## 1. Existing State & Context

- There are currently 224 evidence files in `evidence/`.
- The maximum addition timestamp among all existing evidence files is `2026-09-02T22:21:31+03:00`.
- All existing evidence files were introduced on or before the cutoff date `2026-09-02`.
- Historical evidence files have diverse formats (some with yaml blocks, some with prose, some with measurement tables). Per T1.5 specification, **existing files are untouched**.
- Any new evidence file added after `2026-09-02T23:59:59+03:00` (or uncommitted in working tree) must adhere to the new cryptographic evidence binding standard.

## 2. Header Block Specification

A new evidence file must contain a header block within the first 30 lines (enclosed in ````yaml ... ```` or YAML frontmatter `--- ... ---`) containing the following required keys:
1. `commit:` A valid 40-character or 64-character hex SHA of a Git commit that actually exists in the repository history (`git cat-file -e <commit>^{commit}`).
2. `media_sha256:` Either a 64-character lowercase hex SHA-256 string, or `n/a: no media` (or starting with `n/a:` / `n/a` for tests/findings that do not operate on media files).
3. `host:` A non-empty string indicating the measurement machine (e.g. `HAWAPC01`, `runner-x64`, etc.).
4. `command:` A non-empty string specifying the exact command line or invocation that produced the measured evidence.

## 3. Integration Points

- `tests/test_claims.py`:
  - Add helper function to determine evidence file introduction timestamps using fast `git log --diff-filter=A --name-only --format=COMMIT:%cI -- evidence/`.
  - Add `test_new_evidence_names_its_commit_media_and_host()`:
    - Queries all `*.md` files in `ROOT / "evidence"`.
    - Identifies any file created after cutoff `2026-09-02T23:59:59+03:00` (or uncommitted).
    - Parses the header block.
    - Validates presence and format of `commit:`, `media_sha256:`, `host:`, and `command:`.
    - Verifies via `git cat-file -e <commit>^{commit}` that the referenced commit exists in history.
