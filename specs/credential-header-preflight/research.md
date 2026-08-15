# Research — credential header preflight

Parent: `specs/true-10-10-acceptance/plan.md`, Phase 8.

Serena is unavailable, so `rg` mapped `validate_gemini_key()` to `credential_status()`, the
interactive credential panel, and the credential test suite.

The panel promises never to print a submitted key. Its live transport constructs
`urllib.request.Request` before entering its `try` block. A key containing an embedded newline is
accepted by `getpass().strip()`, then rejected by urllib with a `ValueError` whose message includes
the complete header value. Reproduction with a fake key:

```text
ValueError
Invalid header value b'AIzaSy-THIS-MUST-NOT-PRINT\nInjected: value'
LEAKED True
```

In the interactive CLI that exception is uncaught, so the key reaches stderr/terminal logs in a
traceback. The correct boundary is before any transport or header construction. This is not a
regex-based authenticity check: Google remains the authority on whether a syntactically safe key
is valid. The local check only refuses values that cannot safely be represented as an HTTP API-key
header.

