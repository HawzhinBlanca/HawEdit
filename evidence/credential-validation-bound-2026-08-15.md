# Credential-validation response boundary — 2026-08-15

Candidate branch: `codex/credential-validation-bounds`

Implementation commit: `f28ade1` (the later evidence/floor commits do not change the package
source bytes measured below).

## Reproduced defect

An injected Gemini model-list response with a JSON error containing the submitted key, a NUL, a
newline, and 1,000,000 characters was copied into `KeyCheck.detail`. A status-0 network diagnostic
had the same unbounded/control-bearing behavior. The live `urllib` transport called `read()` with
no byte limit for both successful and HTTP-error responses.

That detail is printed by the credential panel, so the behavior crossed a credential/log boundary;
it was not merely a formatting issue.

## Implemented boundary

- live response streams are read with a 1,048,576-byte ceiling plus one detection byte;
- alternate/injected transport bodies are checked against the same byte ceiling before parsing;
- provider and network diagnostics are normalized to one printable line and capped at 512
  characters;
- the exact submitted credential is replaced before any diagnostic is exposed; and
- ordinary short provider wording remains intact.

Named adversarial regressions:

- `test_key_validation_bounds_and_redacts_an_untrusted_provider_error`
- `test_key_validation_bounds_an_untrusted_network_error`
- `test_the_live_key_probe_refuses_an_oversized_response_without_reading_it_all`
- `test_the_live_key_probe_bounds_an_oversized_http_error_body`

Focused results: 174 credential/Gemini/smoke/CLI tests passed; 79 credential/VEX/policy tests
passed; Ruff, formatting, and strict mypy were clean.

## Canonical gate

The exact `scripts/verify.sh` gate completed in 323.8 seconds:

- Ruff: clean;
- mypy strict: 132 source files, no issues;
- format: 132 files formatted;
- pytest: 2,505 collected, 2,505 passed, zero skipped, 302.19 seconds; and
- JUnit evidence: accepted, with the floor ratcheted from 2,501 to 2,505.

## Source-bound WSL security acceptance

Package source SHA-256:
`5b10f4bbfcd4eccbee7f3dc0abfb650bec488827d8cef2bade3a082b1d039fdd`.

The supported WSL setup/revalidation completed in 176.1 seconds. The live VEX gate then completed
in 143.3 seconds with status `accepted`: 140 exact runtime distributions, two CUDA devices, three
OmniASR assets totaling 43,546,500,168 bytes, and 12 of 12 findings matched to reviewed
dispositions.

The non-overwriting host-local artifact is outside the repository:

`C:\Users\Wareen\AppData\Local\Temp\hawedit-wsl-vex-5b10f4bb-20260815-145909.json`

It is 10,382 bytes with SHA-256
`5aa2b90c1e9005498962512e7bc1b067ca845974b8ff0229bec8320a8f5a2400`.

This local result proves the exact source/dependency/asset/VEX boundary on hawapc01. Promotion still
requires the hosted PR checks and the resulting protected-main SHA's main-only WSL job; this record
does not substitute for either.

