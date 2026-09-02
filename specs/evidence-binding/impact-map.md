# Impact Map — Evidence Binding (`specs/evidence-binding`)

## Affected Modules & Callers

1. **`tests/test_claims.py`**:
   - `test_new_evidence_names_its_commit_media_and_host()` added.
   - Inspects all Markdown files under `evidence/`.
   - Uses `git log` and `git cat-file` to check commit dates and commit existence in history.
   - Zero modifications to existing files or production runtime code.

2. **`evidence/*.md`**:
   - Any future evidence files must carry the bound header.
   - Existing 224 evidence files remain untouched and valid.
