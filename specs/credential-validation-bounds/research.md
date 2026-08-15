# Research — credential validation response bounds

Parent: `specs/true-10-10-acceptance/plan.md`, Phase 8.

Serena is unavailable in this environment, so symbol and caller mapping used `rg` as the
documented fallback.

`credentials._https_get()` is the live, unauthenticated-status transport used by
`validate_gemini_key()`. Unlike the production Gemini transport, it reads the entire success or
HTTP-error body. `validate_gemini_key()` then copies a parsed provider error message into
`KeyCheck.detail`, and the credential panel prints that detail. A proxy/provider response can
therefore consume unbounded memory, preserve control characters, or repeat the credential into
operator logs.

Callers found by `rg`:

- `credential_status()` exposes the result to status checks.
- `credentials.main()` prints the validation detail and decides whether a key may be stored.
- `tests/test_credentials.py` covers valid/rejected/offline responses, header-only auth, and the
  ordinary no-key-leak case, but not a response that itself echoes the submitted key, contains
  control characters, or exceeds a byte/character ceiling.

The production `gemini._https()` boundary already establishes the appropriate design: bounded
stream reads and bounded printable provider diagnostics. Credential validation needs the same
property, plus explicit redaction of the exact submitted key because it is available at this
boundary and must never be copied to `KeyCheck.detail`.

