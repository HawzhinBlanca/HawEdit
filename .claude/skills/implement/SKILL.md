---
name: implement
description: Phase 3 of the CODYSTEM loop for hawedit. Implement ONE approved task test-first via Serena symbolic edits, run scripts/verify.sh, and flip the ledger only if it exits 0. Requires an approved plan.md. Never marks done by judgment.
---

# Implement (one task, then prove it)

**Precondition:** `specs/<feature>/plan.md` has a filled-in `Approved-by:` line. If it does
not, STOP — run `plan` and wait for a human.

## Procedure

Implement only the next unchecked task from `specs/<feature>/tasks.md` — one task, smallest
correct change, test-first:

1. **Write the failing test first.** Name it as the ledger row cites it. Run it and watch it
   fail for the reason you expect; a test that passes before the change proves nothing.
2. **Make it pass.** Edit via Serena symbolic edits. Stay inside the task's impact map — a
   drive-by refactor outside it belongs to a different task.
3. **Run the gate:** `bash scripts/verify.sh`. Not `--fast`; that skips the tests and cannot
   print the success line.
4. **Flip the row, if and only if the gate is green:**
   `bash scripts/update-ledger.sh <feature> T1 test_the_name_you_wrote`
   It re-runs the gate itself, checks every cited test actually ran, flips the one row, and
   records provenance in `specs/<feature>/ledger.log`.
5. Compact what you learned into `plan.md` before starting the next task, and keep context
   under ~50%.

Repeat per task: `T2`, `T3`, … each with its own test names.

## Anti-cheat (these are violations, not shortcuts)
- Do not skip, delete, or `xfail` a test; no `@pytest.mark.skip`; no `-k` / `--deselect` /
  `--ignore` to route around a red suite.
- Do not weaken an assertion, mock the thing under test, or edit a test to match buggy output.
- Do not edit a golden or fixture so it matches your output. §4.3.6's golden render is a pixel
  comparison — changing the reference is changing the answer.
- Do not override the gate's steps. `LINT_CMD`, `TEST_CMD`, `PY` and friends are refused by
  `verify.sh` itself; trying is a bypass attempt, not a configuration.
- Do not hand-edit `scripts/test-count.floor`. If the suite grew, the gate ratchets it — and CI
  fails a run that ratcheted, because the floor and the commit would then disagree.
- Do not write anything into `.gate/`. That is the gate's evidence about itself.
- Never mark a row done from memory. Only `update-ledger.sh` flips one.

## When a test that should pass will not
Say so. `BLOCKED.md` is a numbered list because "cannot be built yet" is a real state in this
project — models that need credentials, hardware that is not here, a labelled set that does not
exist. Add the blocker and cite its number. A skipped test that nobody notices is the quiet
green this whole harness exists to prevent.

## Done when
- `bash scripts/verify.sh` exits 0 and the log ends `VERIFY OK — hawedit gate green`.
- `scripts/update-ledger.sh` flipped the row because the gate passed, not because you decided.
- Required CI checks are green on the pull request — the real source of truth, re-running this
  same gate from committed source on a clean runner.

→ Next: an independent review of the diff against `plan.md`, ideally by a different model.
