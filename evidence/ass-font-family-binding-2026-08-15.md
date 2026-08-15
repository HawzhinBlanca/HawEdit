# ASS font-family binding evidence — 2026-08-15

## Claim

At every Stage 6 burn, HawEdit now binds each Dialogue event's ASS style family to exactly one font
inside the supplied `fonts_dir` and checks Kurdish coverage on that exact file. A different covering
font can no longer certify a missing or non-covering requested family.

## Reproduction and regression

The prior directory-only guard accepts a directory containing:

- `Noto Naskh Arabic`, subset to remove Kurdish keheh U+06A9; and
- an unrelated, renamed copy of the shipped font with full Kurdish coverage.

That is a green directory-level result even though libass is asked for the broken first family. The
new ASS-aware guard selects the requested family and refuses it specifically for U+06A9. Additional
adversarial tests refuse a missing family, two files claiming one family, an undefined Dialogue
style, a malformed style format, and inline `\\fn` family overrides. The shipped ASS resolves to
the exact shipped `NotoNaskhArabic-Regular.ttf` positive control.

The caption/render/pipeline/release/claims/VEX adjacency suite passed 563 tests. No font binary,
golden image, fixture, caption wording, ffmpeg build, or pixel threshold changed.

## Canonical gate

On branch `codex/ass-font-family-binding`, source commit `7e437ff` passed the exact
`scripts/verify.sh` gate in 377.5 seconds:

- Ruff: clean;
- mypy strict: 134 source files, no issues;
- format: 134 files already formatted;
- pytest: 2,520 collected, 2,520 passed, zero skipped, 372.30 seconds; and
- JUnit evidence: accepted, with the test floor ratcheted from 2,513 to 2,520 in commit `2db55fa`.

An earlier wrapper invocation reached its 360-second wrapper timeout without a terminal gate result,
left no child process or floor mutation, and is deliberately not counted as evidence.

## Source-bound WSL security acceptance

Package source SHA-256:
`40c11296da783ed9dc6e1bc259e6c0bd4012d1cc39b1687ae9176e951a37a808`.

`hawedit.wsl_setup --distribution Ubuntu` completed in 305.5 seconds. The source-bound live VEX
gate then completed in 172.6 seconds with status `accepted`:

- 140 exact runtime distributions;
- three exact OmniASR assets totaling 43,546,500,168 bytes;
- two visible CUDA GPUs;
- pinned `pip-audit` 2.10.1 in the exact 29-wheel scanner environment; and
- 12 findings, 12 reviewed dispositions, 12 matches.

The write-once host-local artifact is outside the repository:

`C:\Users\Wareen\AppData\Local\Temp\hawedit-wsl-vex-40c11296-20260815-165603.json`

It is 10,382 bytes with SHA-256
`a9fbda479e0f4de3a862e2a65d92308ed871a04c962d1fd2c03863d6ebd2aefb`.

This proves local source/dependency/asset/VEX readiness. Hosted PR checks and protected-main WSL
acceptance remain separate promotion evidence; this artifact does not substitute for either.
