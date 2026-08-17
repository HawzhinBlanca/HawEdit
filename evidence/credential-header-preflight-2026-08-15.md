# Credential header preflight — 2026-08-15

Candidate branch: `codex/credential-header-preflight`

Implementation commit: `e9732be` (subsequent evidence/floor commits do not change the measured
package source bytes).

## Reproduction

Before the fix, calling `validate_gemini_key()` with a fake value containing an embedded newline
raised outside the transport exception boundary:

```text
ValueError
Invalid header value b'AIzaSy-THIS-MUST-NOT-PRINT\nInjected: value'
LEAKED True
```

The interactive panel accepted that value from hidden input, so the uncaught traceback could copy
the submitted key to stderr despite the module's “never prints the key” invariant.

## Boundary

`validate_gemini_key()` now refuses before transport unless a value is non-empty, at most 512
characters, and entirely printable non-whitespace ASCII (`0x21..0x7e`). This is only an HTTP-header
safety preflight; it does not locally claim a key is authentic. Every header-safe value still goes
to Google's live model-list endpoint for the actual validity decision.

The regressions cover empty, space, tab, CR/LF injection, non-ASCII, and oversized values, plus the
real interactive panel path. The panel case proves zero network calls, zero writes, exit 1, no
traceback, and no submitted-key fragment in either stream.

Focused result: 222 credential/Gemini/smoke/CLI/VEX tests passed; Ruff, formatting, and strict mypy
were clean.

## Canonical gate

The exact `scripts/verify.sh` gate completed in 325.5 seconds:

- Ruff: clean;
- mypy strict: 132 source files, no issues;
- format: 132 files formatted;
- pytest: 2,512 collected, 2,512 passed, zero skipped, 303.53 seconds; and
- JUnit evidence: accepted, floor ratcheted from 2,505 to 2,512.

## Source-bound WSL security acceptance

Package source SHA-256:
`f4d1e4b0c497bf7e1e558c5b0d2d3350263f75da31fc13734886cc766b5daff4`.

Supported WSL setup/revalidation completed in 176.8 seconds and reported OmniASR import success and
two visible CUDA GPUs. The live VEX gate completed in 145.9 seconds with status `accepted`: 140
exact runtime distributions, three exact OmniASR assets totaling 43,546,500,168 bytes, and 12 of
12 findings matched to reviewed dispositions.

The write-once host-local artifact is outside the repository:

`C:\Users\Wareen\AppData\Local\Temp\hawedit-wsl-vex-f4d1e4b0-20260815-152745.json`

It is 10,382 bytes with SHA-256
`3f2415cba8fab59abdd4d5c966d6980d8e482c147e9768c2ae5cdb15ed2b1fab`.

This proves local source/dependency/asset/VEX readiness. Hosted PR checks and the protected-main
WSL job remain mandatory promotion evidence; this local artifact does not substitute for them.

