# Impact map — credential header preflight

| Symbol | Callers | Required behavior |
|---|---|---|
| `validate_gemini_key` | `credential_status`, `credentials.main`, library callers | generic pre-transport refusal for header-unsafe values |
| `credentials.main` | operator/automation stdout and stderr | no key, traceback, write, or network call on refusal |
| `_https_get` | validator default transport | remains the live authority for safe values |

No credential files, secrets, workflows, fixtures, goldens, or enforcement scripts are changed.

