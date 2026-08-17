# Impact map — WSL receipt newline portability

| Changed symbol | Direct callers | Downstream surfaces | Required proof |
|---|---|---|---|
| newline canonicalizer | `package_digest`, `_validate_source_snapshot` | receipt fingerprint and snapshot validation | LF/CRLF equivalence plus semantic-drift refusal |
| `_validate_source_snapshot` | `_publish_source_snapshot`, `load_wsl_runtime_receipt` | WSL producer, model readiness, live VEX gate | full WSL setup tests and canonical gate |

No workflow, credential, model-weight, runtime receipt, or gate implementation is modified in this
unit. A source change will produce a new WSL source digest, so after merge the runtime must be
reprovisioned and the exact-main live VEX job rerun.
