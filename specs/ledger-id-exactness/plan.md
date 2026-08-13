# ledger-id-exactness — plan

## Approach

Escape the dot once, and make every site accept the *same* escaped value. Bash pattern
substitution, no new tool, no new dependency:

```sh
task_re="${task//./\\.}"    # a dot is legal in an id and special in a regex; only . needs it
```

`-` is special only inside a bracket expression and the id is never placed in one; `_` and the
alphanumerics are inert. So `.` is the entire escape set, and enumerating it beats reaching for
a general escaper that would have to be correct about characters the validator already forbids.

**The awk site needs a change of mechanism, not just the escaped value — measured, not reasoned.**
`awk -v task=…` performs escape processing on the assignment, so it turns `T\.` back into `T.`
before the value is ever used as a regex, and the row match succeeds exactly as it does today.
Verified against the script's own extracted program (`scratchpad/escape-probe.sh`, GNU awk, Git
Bash on Windows 11):

| value | `grep -E` at `:67` | `awk -v` at `:102` | `awk` via `ENVIRON` |
|---|---|---|---|
| `T\.`  | no match on `T1` — correct | **matches `T1`** — the defect survives | no match — correct |
| `T\\.` | no match, for the wrong reason | no match — correct | n/a |

Using `-v` would therefore require `T\.` at the grep sites and `T\\.` at the awk site: two
different escapings of one value, three lines apart. That asymmetry is precisely the shape of the
bug being fixed, so the plan takes the other branch — pass the value through the environment,
which does no escape processing:

```sh
TASK_RE="$task_re" awk '… task = ENVIRON["TASK_RE"] …'
```

One escaped value, correct at all four sites. Confirmed for the plain id `T1` (still matches), the
legitimate dotted id `T1.2` (still matches) and the attack `T.` (no longer matches).

**Methodology note, because it invalidated an earlier attempt.** Backslash-bearing probes typed
directly into a shell command are rewritten before the shell sees them — `'T\.'` and `'T\\.'`
reached bash as identical bytes, which made a first round of this measurement report the opposite
conclusion. The table above comes from a script written to a file and then executed. Any future
work on this line should do the same.

`task_re` then replaces `$task` at `:67`, `:72` and in the `-v task=` passed to awk at `:102`.
The messages keep printing the *unescaped* `$task`, because an operator who typed `T.` should be
told `T.` was refused, not `T\.`.

**The same escape is applied to each citation at `:91`, and that site matters more.** `:60`
permits `.` in a cited test name and `:91` interpolates it into the report lookup, so a citation
naming no real test can be confirmed by the evidence check. Reproduced against a report holding
`test_alpha` / `test_alqha`: the citation `test_al.ha` is accepted by the validator and reported
present. That defeats the stated purpose of the check at `:11-16` — catching a citation "against
evidence rather than against the agent's word" — which makes it a forged-evidence path in the
anti-cheat machinery rather than a cosmetic exactness bug. The escape happens inside the existing
`for cite in "${cites[@]}"` loop; the `(\[[^"]*\])?` parametrisation suffix is untouched, since it
is the script's own regex and not interpolated input.

**Why not narrow the alphabet.** Dropping `.` from `:49` is a smaller diff and closes the same
hole, and it is the wrong trade: `PROGRESS.md` numbers milestones `M0.12` and `M7.3`, so dotted
ids are this project's own idiom. A fix that forbids `M0.12` as a task id solves the defect by
removing the feature. Recorded here so the cheaper option is visibly considered and rejected,
not overlooked.

## Files and symbols

| file | change |
|---|---|
| `scripts/update-ledger.sh` | one new line after the validator (`task_re`); `:67` and `:72` use it; `:102` switches from `-v task=` to `ENVIRON["TASK_RE"]`; the `for cite` loop gains the same escape for `:91`. **Enforcement surface** — needs `.codystem-allow-self-edit` created before and deleted after |
| `tests/test_harness_scripts.py` | 2 new tests, reusing the existing `sandbox`/`write_ledger`/`gate_ran`/`run_ledger` helpers |
| `scripts/test-count.floor` | ratcheted 1659 → 1661 by the gate, committed in the same commit |

## Tests, each mapped to a criterion

| test (exact pytest name) | AC |
|---|---|
| `test_the_ledger_flipper_treats_a_dot_in_a_task_id_as_a_literal` | AC1, AC3 |
| `test_the_ledger_flipper_still_matches_a_genuinely_dotted_task_id` | AC2, AC8 |
| `test_the_ledger_flipper_short_circuits_only_the_literal_dotted_row` | AC4 |

AC5–AC7 (the citation site) get **no test**, because the check runs below `:78` and pytest cannot
reach it. They are held by the by-hand reproduction recorded in the ADR. This is the second time
this structural limit has bitten; it is now the single largest hole in the harness's own coverage
and deserves its own feature — see the finding in `impact-map.md`.

The second is the one that matters. It writes a ledger holding `- [ ] T1.2 …`, asks for `T1.2`,
and asserts the stub gate **was** reached — `gate_ran(root) is True`. That is the only available
proof that the row check passed, since everything after the gate is unreachable from pytest
(D-199), and it is what stops the fix from closing the hole by breaking legitimate ids.

Both tests fail before the change: the first because `T.` currently matches `T1` and so reaches
the gate instead of being refused; the second passes before and after, and exists to hold AC5
rather than to demonstrate the bug. Stated plainly because a test-first claim about a test that
was always green is worth nothing.

## Risks

- **Self-edit visibility.** The sentinel must be deleted before committing; a commit containing
  `.codystem-allow-self-edit` would ship the unlocked state. Verify with `git status` before and
  after.
- **Quoting.** `${task//./\\.}` inside an already-quoted `grep -qE "…${task_re}…"` is the kind of
  thing no local linter checks — D-162 put shellcheck in CI only. The two tests are the guard.
- **awk's second escape layer.** The awk pattern is built by string concatenation
  (`"^- \\[ \\] " task "([ \t]|$)"`), so the value arrives as an ERE fragment exactly as the grep
  does. `\.` is correct in both. Verify by running the extracted program, as `research.md` did.
- **Concurrent session.** BLOCKED #12 is live and a second session has committed to this branch
  during the previous feature. The sentinel file is repo-root and shared; if that session is
  mid-edit, creating it changes what its guard permits. Prefer a quiet moment, and delete it
  immediately after.

## Divergence and dependencies

No BLUEPRINT § touched, no runtime dependency added, no licence to audit. D-199 already records
the defect; this feature closes it, so the ADR owed at the end is a short amendment naming the
fix and the reproduction, not a new decision.

Approved-by:
