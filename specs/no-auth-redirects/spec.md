# Specification — no authentication redirects

Parent: true-10/10 AC-10 and AC-12.

1. WHEN an authenticated HTTP request receives any redirect, THE HawEdit transport SHALL refuse the
   redirect and SHALL NOT contact the target.
2. WHEN the refused request carries a Developer API key or Vertex bearer token, THE target SHALL
   receive neither header.
3. WHEN a redirect is refused, THE existing credential and Gemini boundaries SHALL convert the 3xx
   response into their normal bounded, non-secret failure result.
4. WHEN the endpoint returns a direct response, THE existing bounded response, token, billing, and
   schema behavior SHALL remain unchanged.

Evidence tests:

- `test_authenticated_http_never_contacts_a_redirect_target`
- migrated live-transport response-bound tests in `test_credentials.py` and `test_gemini.py`
- existing one-billed-call, lazy-auth, and provider-error suites
