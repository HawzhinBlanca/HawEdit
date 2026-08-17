# Authenticated HTTP no-redirect evidence — 2026-08-15

## Claim

HawEdit's Gemini Developer, Vertex, and credential-validation requests refuse every HTTP redirect
before Python can forward an API-key or bearer header to the target. Unauthenticated Omni asset
transport is intentionally outside this change.

## Adversarial reproduction and regression

Before the fix, the supported CPython default `urllib` redirect handler contacted a second local
loopback server and forwarded both fake `x-goog-api-key` and `Authorization` headers. The new real
two-server regression receives the same redirect and proves that the target is never contacted:

- `tests/test_http_transport.py::test_authenticated_http_never_contacts_a_redirect_target`
- credential and Gemini response-bound mocks now exercise the shared no-redirect seam; and
- the 513-test cloud/pipeline/release/claims/VEX adjacency slice passed.

No real credential or provider request was used.

## Canonical gate

On branch `codex/no-auth-redirects`, source commit `e59d46d` passed the exact
`scripts/verify.sh` gate in 330.2 seconds:

- Ruff: clean;
- mypy strict: 134 source files, no issues;
- format: 134 files already formatted;
- pytest: 2,513 collected, 2,513 passed, zero skipped, 316.14 seconds; and
- JUnit evidence: accepted, with the test floor ratcheted from 2,512 to 2,513 in commit `c002f9a`.

## Source-bound WSL security acceptance

Package source SHA-256:
`ab273c0b76a53ca4a405b85bbc7333420ea4f83e2bd152316058bcb838c53226`.

`hawedit.wsl_setup --distribution Ubuntu` completed in 177.9 seconds. The source-bound live VEX
gate then completed in 144.2 seconds with status `accepted`:

- 140 exact runtime distributions;
- three exact OmniASR assets totaling 43,546,500,168 bytes;
- two visible CUDA GPUs;
- pinned `pip-audit` 2.10.1 in the exact 29-wheel scanner environment; and
- 12 findings, 12 reviewed dispositions, 12 matches.

The write-once host-local artifact is outside the repository:

`C:\Users\Wareen\AppData\Local\Temp\hawedit-wsl-vex-ab273c0b-20260815-160544.json`

It is 10,382 bytes with SHA-256
`4a6a9127b9a6115225a16700e6e161eadf4e4d8d29d3d67b784ca0aed3045249`.

This proves local source/dependency/asset/VEX readiness. Hosted PR checks and protected-main WSL
acceptance remain separate promotion evidence; this artifact does not substitute for either.
