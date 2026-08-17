# AGENTS.md — Operating rules for AI coding agents

> **This file is the single source of truth for operating rules and gate commands.** If any
> other doc (README, BLUEPRINT, PROGRESS) disagrees with the commands here or with
> `scripts/verify.sh`, this file and `verify.sh` win. Read natively by Claude Code, Codex,
> Copilot and Gemini; `CLAUDE.md` is a thin bridge that imports it.

## Project
hawedit — a Kurdish (Sorani/ckb) video repurposing system implementing `BLUEPRINT.md` v1.1.
Python 3.11+, venv + pip, pytest / ruff / mypy --strict. `BLUEPRINT.md` is frozen: its §
numbers are the spec, and a divergence from it needs an ADR in `DECISIONS.md`, not a commit
message.

## Commands (exact)
- Setup:     `bash scripts/setup.sh`            # fresh clone → green gate, one command
- Fast:      `bash scripts/verify.sh --fast`    # lint + typecheck only — NOT the gate
- Verify ALL: `bash scripts/verify.sh`          # run before claiming any task done
- Ledger:    `bash scripts/update-ledger.sh <feature> <TASK> <test_name[,...]>`
- Pipeline:  `.venv/bin/python -m hawedit.pipeline VIDEO.mp4 --work-dir work`
- Models:    `.venv/bin/python -m hawedit.models`     # §7 checkpoint readiness, reports only
- ffmpeg:    `bash scripts/fetch-ffmpeg.sh`           # pinned + checksummed, libass/HarfBuzz

On Windows the interpreter is `.venv/Scripts/python.exe`. Both `setup.sh` and `verify.sh`
already handle either layout; hardcode neither.

`verify.sh` runs, in order: `ruff check` → `mypy` → (stop here on `--fast`) →
`ruff format --check` → `pytest --junitxml=.gate/last-test-run.xml` → `hawedit.gate` grading
that report for freshness and count. All three scoped to `src tests scripts`.

**The gate's steps are not configurable.** `LINT_CMD`, `FORMAT_CMD`, `TYPECHECK_CMD`,
`TEST_CMD` and `PY` are refused, not honoured (exits 3 and 5). Do not try to route around
that — for a partial check the answer is `--fast`, which cannot print the success line.

## Workflow (non-negotiable)
1. **RESEARCH before coding.** Use Serena (`find_symbol`, `find_referencing_symbols`) to map
   the real code. Write `specs/<feature>/research.md`. Do NOT write code yet.
2. **PLAN.** Write `specs/<feature>/plan.md` + `impact-map.md`. **STOP and wait for human
   approval** on the `Approved-by:` line.
3. **IMPLEMENT one task at a time**, smallest correct change, test-first. After each task run
   `bash scripts/verify.sh`. Only if it exits 0, flip the row with `scripts/update-ledger.sh`.
4. **Never mark a task or feature "done" or "complete" on your own judgment.** "Done" =
   `verify.sh` green AND the required CI checks green on the pull request. CI re-runs this
   same gate from committed source on a clean runner; a local pass cannot speak for it.

## Grounding rules
- Find the symbol with Serena before editing it. Never invent a function signature.
- Before changing any symbol, run `find_referencing_symbols` and list the affected callers in
  `impact-map.md`. Add or adjust tests for every caller you might break.
- Cite `BLUEPRINT.md` by § when a change implements or diverges from the spec, `BLOCKED.md` by
  number when something cannot be built yet, `DECISIONS.md` by D-number when a choice was
  already settled.
- **A number carries the hardware and library versions it was measured on.** Report a
  measurement with where it came from, or do not report it. Judgment recorded as judgment is
  fine; judgment presented as a measurement is not.

## Hard boundaries (also enforced by hooks — do not attempt to bypass)
- **Never edit:** `.env*`, `secrets/**`, `**/*.pem`, `.venv/**`, `.venv-wsl/**`, `.gate/**`,
  `.ffmpeg/**`, `models/**` (except `sources.json` and `revisions.json`), `build/**`,
  `dist/**`, `*.egg-info/**`.
  `.gate/` is where the gate writes the test report it then grades itself against — hand-writing
  it is forging the evidence D-093 exists to produce.
- **Enforcement surface** — `scripts/verify.sh`, `scripts/guard-pretooluse.sh`,
  `scripts/claude-stop-verify.sh`, `scripts/update-ledger.sh`, `scripts/test-count.floor`,
  `src/hawedit/gate.py`, `.claude/settings.json`, `.github/**`, `tests/golden/**`,
  `tests/fixtures/**`. Improving the harness is legitimate work, so these are editable — but
  only after creating `.codystem-allow-self-edit`, which shows up in `git status` and makes the
  self-edit deliberate and visible instead of quiet.
- **Never run:** `rm -rf`, `git push --force` / `--force-with-lease`, `git reset --hard` on a
  shared branch, `git commit|push --no-verify` or `-n`, `curl … | sh`.
- **Never commit secrets.** Never disable a failing test to make CI pass.

## Anti-cheat (violations, not shortcuts)
- Do not skip, delete, or `xfail` a test; do not add `@pytest.mark.skip`, and do not reach for
  `-k` / `--deselect` / `--ignore` to make a red suite look green.
- Do not weaken an assertion, mock the thing under test, or edit a golden or fixture so it
  matches buggy output. §4.3.6's golden render is a pixel comparison — changing the reference
  is changing the answer.
- Do not hand-edit `scripts/test-count.floor`. The gate ratchets it; CI fails the run if a gate
  ratcheted it, because the evidence and the claim would be out of step.
- Do not mark a row done from memory. Only `scripts/update-ledger.sh` flips one, and only after
  the gate passed and every cited test was found in the report that run wrote.

## Context hygiene
Keep the context window under ~50%. Use subagents for searches and log reading and keep only
their summaries. Compact findings into `research.md` / `plan.md`, then continue in a fresh
context. `DECISIONS.md` and `PROGRESS.md` are hundreds of KB — grep them, never read them whole.

## Acceptance criteria format
Use EARS in `specs/<feature>/spec.md`: "WHEN \<trigger\>, THE \<system\> SHALL \<response\>".
Every criterion maps to at least one named automated test, and that test's name is what gets
cited when the row is flipped.

## Living docs (keep small; update when behavior changes)
- `BLUEPRINT.md`   — frozen spec, § numbered. Diverging needs an ADR.
- `DECISIONS.md`   — ADRs, `## D-NNN`. A new runtime dependency or architectural change
                     requires one. Licences are audited here; NonCommercial is a hard reject.
- `PROGRESS.md`    — what is built, with evidence.
- `BLOCKED.md`     — numbered blockers. Cite the number rather than working around it silently.
- `evidence/`      — measurement records, one file per claim worth checking later.
