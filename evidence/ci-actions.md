# GitHub Actions source identity — 2026-08-09

The gate previously executed moving major-version tags. The official action repositories were
queried with `git ls-remote` and the tag refs resolved as follows:

| Action tag | Full commit used by the workflow |
|---|---|
| `actions/checkout@v4` | `11d5960a326750d5838078e36cf38b85af677262` |
| `actions/setup-python@v5` | `a26af69be951a213d495a4c3e4e4022e16d87065` |

`.github/workflows/gate.yml` now uses the commits while keeping the tag names in comments for
human update context. `tests/test_fetch_scripts.py` scans every workflow and refuses any remote
`uses:` target that is not a full 40-hex commit. Local actions and `docker://` images are treated
separately because they do not have this `owner/repo@commit` form.

The first workflow-dispatch run after this change is the runtime evidence that both pinned action
commits still execute successfully; a local YAML assertion alone cannot prove GitHub can fetch
and run them.
