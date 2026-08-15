# Impact map — credential validation response bounds

| Symbol | Callers/consumers | Required verification |
|---|---|---|
| `credentials._https_get` | `validate_gemini_key` default transport | bounded success and HTTP-error reads |
| `credentials.validate_gemini_key` | `credential_status`, `credentials.main`, direct library callers | printable, bounded, exact-key-redacted detail |
| `credentials.KeyCheck.detail` | CLI/status output | ordinary detail preserved; hostile detail cannot escape |
| `tests/test_credentials.py` | canonical gate | provider, network and stream-bound adversaries |

No credential file, secret, workflow, fixture, golden, or enforcement surface changes.

