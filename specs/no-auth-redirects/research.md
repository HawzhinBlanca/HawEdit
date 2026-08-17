# Research — no authentication redirects

Parent: `specs/true-10-10-acceptance/plan.md`, Phase 8.

Serena is unavailable; `rg` mapped every `urlopen` call and every `x-goog-api-key`/`Authorization`
header in `src/hawedit`.

The release gate already uses a no-redirect opener because Python's default redirect handler copies
authentication headers. The Gemini Developer and Vertex transports, and the credential model-list
probe, still used default `urllib.request.urlopen`.

A local two-server reproduction on the supported CPython 3.12 runtime sent a request with fake
`x-goog-api-key` and bearer headers to a redirecting source. The unrelated target received both:

```text
X_GOOG_FORWARDED FAKE-SECRET
AUTH_FORWARDED Bearer FAKE-TOKEN
```

The Google endpoints are hardcoded HTTPS origins, but the security property must not depend on a
provider, proxy, or compromised endpoint never redirecting. Neither API contract requires redirects;
an HTTP 3xx should be surfaced as a bounded provider refusal without contacting its target.

`omni_assets.py` also uses `urlopen`, but it carries no credential header and legitimately follows
the upstream asset transport; it is outside this unit. `release.py` is already protected.
