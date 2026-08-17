# Project Constitution — hawedit

The rules a plan is checked against. `AGENTS.md` says how to work; this says what the work has
to be true of.

## Layout
Each feature gets `specs/<feature>/` containing:

| file | written by | what it is |
|---|---|---|
| `spec.md` | human or agent | EARS acceptance criteria |
| `research.md` | `research` | the real symbols and data flows, ≤ ~60 lines |
| `plan.md` | `plan` | approach + the `Approved-by:` line a human fills in |
| `impact-map.md` | `plan` | every symbol to be touched, its callers, their tests |
| `tasks.md` | `plan` | the ledger; rows flip only via `scripts/update-ledger.sh` |
| `ledger.log` | `update-ledger.sh` | provenance — which gate run flipped which row, when |

## Principles
- **Test-first.** No implementation code before a failing test exists for the criterion.
- **Smallest correct change.** No drive-by refactors outside the task's impact map.
- **The gate decides done.** Not the agent, not the diff's plausibility. `verify.sh` green, then
  CI green on the PR. A run that proves nothing cannot be green — that is why the gate refuses
  overridden steps, checks its interpreter can import the project, and grades its own test
  report instead of trusting its exit code.
- **BLUEPRINT.md is frozen.** Implementing a § is normal work. Diverging from one requires an
  ADR in `DECISIONS.md` first.
- **A new runtime dependency or architectural change requires an ADR** (`## D-NNN` in
  `DECISIONS.md`), including the licence. NonCommercial is a hard reject (D-002).
- **A number carries the hardware and library versions it was measured on.** §8.1's rule
  generalises: report where a measurement came from, or do not report it. Judgment recorded as
  judgment is fine; judgment dressed as a measurement is not.
- **Blocked is a real state.** `BLOCKED.md` is numbered so that "cannot be built yet" can be
  cited instead of silently worked around. A `skipif` nobody notices is worse than a red test.
- **Observability.** Non-trivial paths carry structured logs; a stage that can half-succeed says
  which half.
- **Security.** Never log secrets. Validate all external input. The credentials panel refuses to
  write anywhere git tracks — keep it that way.
