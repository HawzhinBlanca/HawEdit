# harness-hardening — plan

Five holes, four tasks, ordered by what each protects rather than by how hard it is.

## T1 — `gate.yml`'s two anti-skip steps (AC1–AC3)

**The only hole CI does not wash out.** Both steps pipe pytest through `tee` and then `grep` for
"skipped". `tee` discards the exit status, and neither "1 deselected" nor "no tests ran" nor
"ERROR: file or directory not found" contains that word — so a rename retires §4.3.6's Kurdish
golden pixel comparison and CI stays green.

The fix is the idiom already present at `:110` in the same file: `set -o pipefail`, capture `rc`,
refuse a non-zero. Two steps, three lines each.

Testable without a runner: parse `.github/workflows/gate.yml` and assert no step pipes pytest
without `pipefail`. That is AC3, and it is what keeps the fix from being undone later.

## T2 — refuse `PYTEST_ADDOPTS` (AC4–AC6)

`verify.sh:69-72` already loops over `LINT_CMD FORMAT_CMD TYPECHECK_CMD TEST_CMD` and refuses any
that is set. `PYTEST_ADDOPTS` reconfigures the test step without being one of them, and a
nine-line plugin loaded that way turns a failing suite green while `--check-tools` still passes.
Adding it to that existing list is a one-word change and reuses the exit code the Stop hook
already maps.

**`PYTHONPATH` is deliberately left out, and this is the decision to take.** Refusing a non-empty
`PYTHONPATH` closes the same hole more completely and may break legitimate local setups —
editable installs, a WSL runner, a developer's own tooling. Refusing `PYTEST_ADDOPTS` alone
closes the demonstrated attack and nothing else. Recommend the narrow fix; the wide one is yours
to call.

A fuller fix exists and is not proposed here: `gate.py` could assert the set of loaded pytest
plugins against an allowlist, which would catch entry-point plugins too. It is a larger change to
the program that grades the evidence, and it deserves its own spec rather than riding along.

## T3 — a run token on the report (AC7–AC9)

`verify.sh:62` fixes the report path, `:128` deletes it, `:133` grades it with `$started_at`.
`gate.py:194` refuses a report *older* than the run — a one-sided bound. Nothing refuses one
written by a different run after this one started, and there is no lock, pid or trap anywhere in
`verify.sh`.

Write a token at `rm -f` time; have `gate.py` require it. The token belongs somewhere the report
carries it — a sibling file written next to the report and compared by mtime-and-content is the
smallest version; embedding it in the XML would mean `TEST_CMD` composing it, which is exactly
the configurability the gate refuses.

Under BLOCKED #12 this is not hypothetical: `.gate/last-test-run.xml` was rewritten at 02:30 on
2026-08-13 by a run that was not this session's.

## T4 — normalise before matching (AC10–AC14)

H2 and H3 are one bug in two places. The guard compares a rendering against a rule:
`.gate\last-test-run.xml` and `'.gate/last-test-run.xml'` and `$f` all denote a protected path and
none of them matches a glob written with forward slashes and no quotes.

Normalise the candidate before `should_block`: convert backslashes to forward slashes, lowercase
the comparison on the directory components the rules name, strip surrounding quotes, and refuse
outright any write target containing `$` — the guard cannot know what a variable holds, and
refusing is the only safe answer.

`scripts/guard-test.sh`'s 56 checks are the regression suite for this and must stay green; a
normalisation that over-blocks makes the harness unusable, which is a worse outcome than the hole.

## Risks

- **Every task edits an enforcement file.** Each needs `.codystem-allow-self-edit` created and
  deleted within the task, visible in `git status` while it exists, and absent from every commit.
- **No local shellcheck** (D-162) — T1 and T4 are shell changes whose lint runs only on CI.
- **T4 changes what the guard blocks.** Over-blocking is the failure mode to watch; the 56 checks
  plus the new criteria are the evidence either way.
- **T3 touches the two files that decide what green means.** It is the one task where a mistake
  makes the gate refuse honest runs, so it should land last and alone.

## Divergence and dependencies

No BLUEPRINT § is implemented or diverged from — the enforcement harness is outside the frozen
spec (`specs/constitution.md:25-26`). No new runtime dependency, so no licence to audit and no
D-002 question. One ADR is owed at the end recording what was closed, what was left open by
choice (`PYTHONPATH`, the verb list, the plugin allowlist), and the measurements.

Approved-by:
