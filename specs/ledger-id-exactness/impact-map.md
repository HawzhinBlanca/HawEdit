# ledger-id-exactness — impact map

Grounding caveat: found with ripgrep, not `find_referencing_symbols` — Serena is not connected.

## Symbol changed

`scripts/update-ledger.sh` — the shell variable `$task` at three interpolation sites (`:67`,
`:72`, `:102`), gaining an escaped sibling `task_re`. No function signature exists to break; it
is a 123-line shell script with no library surface.

## Callers

| caller | kind | test covering it |
|---|---|---|
| none in code | `grep -rn "update-ledger"` finds only prose: `AGENTS.md:35`, `AGENTS.md:88`, `.claude/skills/plan/SKILL.md`, `.claude/skills/implement/SKILL.md`, `specs/constitution.md:15` | n/a |
| the 8 refusal tests added in `3b83897` | `tests/test_harness_scripts.py` | they are the coverage; all 8 must stay green |
| a human or agent at a shell | invocation | `specs/harness-integrity/ledger.log` shows the only three real invocations to date |

## Every existing test that touches the changed lines

These must all still pass — the fix moves the value used at `:67`, which is the line five of
them assert against:

- `test_the_ledger_flipper_refuses_a_task_id_with_no_row` — `T99`, no dots, must still refuse
- `test_the_ledger_flipper_does_not_prefix_match_a_longer_task_id` — `T1` vs a `T10`-only
  ledger; the anchoring this depends on is untouched, but it is the closest neighbour to the
  change and the first place a bad escape would show
- `test_the_ledger_flipper_short_circuits_a_row_already_marked_done` — `:72`, the second
  interpolation site, and the one easiest to forget when changing `:67`
- `test_no_refusal_path_reaches_the_gate` — the sentinel test; a fix that accidentally let `T.`
  through would trip this too
- `test_the_ledger_flipper_refuses_a_task_id_outside_the_allowed_set` — the validator at `:49`
  must be left exactly as it is; this test pins the alphabet and would catch a narrowing "fix"

## The largest hole in the harness's own coverage — finding, and a named follow-up

Everything below `update-ledger.sh:78` is unreachable from pytest, because the gate refuses a
nested full run and pytest runs underneath it. That is now blocking twice: it blocked the flip
and provenance in `harness-integrity`, and it blocks AC5–AC7 here — the citation check, which is
the evidence check, and the site where the more serious of the two defects lives.

The structural fix is to make the flipper's post-gate half callable without a gate: a flag that
performs the citation check and the flip against a *supplied* report path and a supplied
verdict, so a test can drive it with a fixture report and no gate at all, while the real
invocation path stays exactly as it is. That is a change to the enforcement script's interface,
needs its own spec, and is deliberately not attempted here. Named so it is a decision rather than
a gap nobody wrote down.

## Caller with no test — finding

The awk program at `:102-112` receives `task` through `-v`, and **no test reaches it at all**:
everything below `:78` is unreachable from pytest (D-199). The fix changes what that awk
receives, and the tests can only prove the *grep* side of it. That gap is real and is not closed
by this feature. The reproduction method in `research.md` — extracting the awk program with
`sed` and running it directly — is the available substitute, and it should be re-run by hand
after the change and its output recorded in the ADR. Written here as a finding rather than left
implicit, because "the tests are green" will not cover this line.

## Shared mutable state

| state | by this feature | mitigation |
|---|---|---|
| `.codystem-allow-self-edit` | created, then deleted | repo-root and shared with a live second session (BLOCKED #12); delete immediately after the edit and verify with `git status` |
| `scripts/test-count.floor` | 1659 → 1661 | committed with the tests |
| `.gate/last-test-run.xml` | rewritten by each gate run | unchanged risk; the new tests use the tmpdir sandbox |
