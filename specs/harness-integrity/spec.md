# harness-integrity — acceptance criteria (EARS)

Scope: automated coverage for the two CODYSTEM enforcement scripts that have none.
Neither script is modified. See `research.md` for grounding.

## The ledger flipper — `scripts/update-ledger.sh`

Every criterion below concerns a refusal that fires **before** `scripts/verify.sh` is invoked
at `update-ledger.sh:78`.

- **AC1** WHEN `update-ledger.sh` is invoked with fewer than three arguments, THE ledger flipper
  SHALL print usage to stderr and exit 2.
- **AC2** WHEN the named feature has no `specs/<feature>/tasks.md`, THE ledger flipper SHALL
  refuse with exit 2 and name the missing path.
- **AC3** WHEN the task id contains any character outside `[A-Za-z0-9_.-]`, THE ledger flipper
  SHALL refuse with exit 2.
- **AC4** WHEN a cited test name is not a plain test name, THE ledger flipper SHALL refuse with
  exit 2.
- **AC5** WHEN no row in the ledger matches the task id, THE ledger flipper SHALL refuse with
  exit 2.
- **AC6** WHEN the ledger contains a longer task id sharing the requested id as a prefix, THE
  ledger flipper SHALL NOT treat it as a match.
- **AC7** WHEN the requested row is already marked `[x]`, THE ledger flipper SHALL report
  nothing to do and exit 0.
- **AC8** WHEN any of AC1–AC7 fires, THE ledger flipper SHALL NOT invoke `scripts/verify.sh`.

## The Stop hook — `scripts/claude-stop-verify.sh`

- **AC9** WHEN the gate exits 0, THE Stop hook SHALL exit 0.
- **AC10** WHEN the gate exits 1, THE Stop hook SHALL exit 2.
- **AC11** WHEN the gate exits 2, THE Stop hook SHALL exit 1.
- **AC12** WHEN the gate exits 3, THE Stop hook SHALL exit 2.
- **AC13** WHEN the gate exits 4, THE Stop hook SHALL exit 1.
- **AC14** WHEN the gate exits 5, THE Stop hook SHALL exit 2.
- **AC15** WHEN the gate exits a code the map does not name, THE Stop hook SHALL exit 2.
- **AC16** WHEN the payload on stdin carries `"stop_hook_active": true`, THE Stop hook SHALL
  exit 0 without invoking the gate.

## Explicitly out of scope (recorded, not waved off)

- The half of `update-ledger.sh` below line 78 — the citation check (`:88-97`), the awk flip
  (`:102-113`) and the provenance line (`:117-119`). Reaching it requires `verify.sh` to exit 0,
  but pytest runs *under* the gate, which exports `HAWEDIT_GATE_DEPTH` (`verify.sh:100-101`) and
  refuses a nested full run with exit 4 (`verify.sh:117-118`). Covered instead by running the
  real script by hand against this feature's own `tasks.md` — see `plan.md` Definition of Done.
- `scripts/guard-pretooluse.sh`, already covered by `scripts/guard-test.sh` (56 checks,
  `.github/workflows/gate.yml:42`).
