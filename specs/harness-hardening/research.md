# harness-hardening — research

Grounding caveat: Serena is not connected; everything below is ripgrep, full reads and
reproductions, cited file:line. Each hole has its own measurement record in `evidence/` — this
file is the index, not a re-derivation.

## The five holes, all reproduced

| # | hole | record | scope |
|---|---|---|---|
| H1 | the gate certifies an **augmented** pytest | `evidence/the-gate-certifies-an-augmented-pytest.md` | local |
| H2 | the guard's `file_path` boundary is inert on Windows | `evidence/the-guards-path-boundary-is-inert-on-windows.md` | local, Windows |
| H3 | the write-target scan compares shell words to path globs | `evidence/the-write-target-scan-matches-shell-words-not-paths.md` | local, all platforms |
| H4 | CI's anti-skip steps are blind to a test that never ran | `evidence/the-anti-skip-guards-cannot-see-a-test-that-never-ran.md` | **CI** |
| H5 | the gate cannot tell its report from a concurrent run's | `evidence/the-gate-cannot-tell-its-own-report-from-another-runs.md` | local |

## What they have in common

H2, H3 and H5 are one failure shape: a check compares a *rendering* of a thing against a rule
while something else resolves the thing — a path spelling on Windows, a shell word before quote
removal, a report with no provenance. H1 is adjacent: `gate.py:59` verifies where three module
*names* live and never asks what those modules then load.

H4 is the odd one and the most urgent, because it is the only one CI does not wash out.

## Files and symbols

- `src/hawedit/gate.py:59` `GATE_TOOLS`; `:62-111` `assert_tools_are_from_this_environment`;
  `:194` the one-sided freshness bound; `:246-247` the ratchet.
- `scripts/verify.sh:62` `TEST_REPORT` (fixed path); `:69-72` the override refusal loop, covering
  `LINT_CMD FORMAT_CMD TYPECHECK_CMD TEST_CMD` only; `:82` the composed `TEST_CMD`; `:128`
  `rm -f "$TEST_REPORT"`; `:133` the grading call. No `flock`, no pid, no trap anywhere.
- `scripts/guard-pretooluse.sh:96-111` `is_protected_path`; `:113-129` `is_enforcement_path`;
  `:185-196` the write-target candidate extraction.
- `.github/workflows/gate.yml:81-90` and `:96-103` the two anti-skip steps; `:110` the third,
  which is correct and shows the idiom the other two lack.

## Existing test surface this can build on

`tests/test_harness_scripts.py` already carries the sandbox pattern (copy a script into
`tmp_path`, give it a stub `verify.sh`, drive it with a payload) plus the hook-wiring assertions
that read `.claude/settings.json` directly. `tests/test_gate.py` and `tests/test_gate_evidence.py`
cover `gate.py` in-process. Between them every fix below has a home.

## Blockers and prior decisions that constrain this

- **BLOCKED #12** (live) — two sessions share this checkout. H5 is a consequence of it, not a
  hypothetical, and the sentinel file H2/H3's fixes interact with is repo-root and shared.
- **D-092 / D-093** — the gate must not trust a substituted tool. Any fix for H1 must not become
  a second, half-correct copy of that rule; `verify.sh:157-161` already says why the guard
  deliberately does not duplicate the override refusal.
- **D-162** — shellcheck runs in CI only, so a quoting mistake in a guard fix surfaces on the
  runner, not locally.
- **D-198** — the enforcement surface is editable only behind `.codystem-allow-self-edit`.

## Risks specific to fixing these

- Every fix touches an enforcement file. All of them need the sentinel, created and deleted
  inside one task, visible in `git status` while it exists.
- H1's obvious fix — refusing `PYTHONPATH` outright — may break legitimate local setups. Refusing
  `PYTEST_ADDOPTS` is narrow and safe; refusing a non-empty `PYTHONPATH` is not, and that
  asymmetry is a decision rather than an implementation detail.
- H2's fix changes what the guard blocks. A normalisation bug that over-blocks makes the harness
  unusable; `scripts/guard-test.sh`'s 56 checks are the regression suite and must stay green.
