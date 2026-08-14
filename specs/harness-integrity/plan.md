# harness-integrity — plan

## Approach

One new test file, `tests/test_harness_scripts.py`. **No script is modified**, no production
symbol is touched, no runtime dependency is added.

Both scripts resolve their own repo root from their own location —
`update-ledger.sh:25-26` and `claude-stop-verify.sh:29-30` both do
`here="$(cd "$(dirname "$0")/.." && pwd)"; cd "$here"`. So copying a script into
`tmp_path/scripts/` makes that tmpdir its world. Every test therefore runs against a sandbox
holding a **stub** `scripts/verify.sh`, never the real one.

That single property buys three things at once:
- tests are milliseconds, not the 2m40s the real gate costs;
- nothing touches `.gate/last-test-run.xml` or `scripts/test-count.floor`, so a concurrent
  session (BLOCKED #12, live — a second session pushed `ff77942` mid-session) cannot corrupt a
  run and this run cannot corrupt theirs;
- the stub can *record that it ran*, which is how AC8 is proved rather than assumed: the stub
  writes a marker file, and each refusal test asserts the marker does not exist.

The stub-gate technique is not novel here — D-198 (`DECISIONS.md:10263`) exercised the Stop
hook against "a stub gate returning each of 0,1,2,3,4,5,9". This commits that exercise as a
test instead of leaving it as a sentence in an ADR.

**Why a stub gate is legitimate and does not violate D-092/D-093.** Those ADRs forbid faking the
*gate's own tools* — a fake `pytest` on `PYTHONPATH` forged a green and ratcheted the floor
(D-093, `DECISIONS.md:3762`), and `PY` replaced every step including the one that grades the
others (D-092, `:3706`). Neither script under test is the gate. `claude-stop-verify.sh`'s entire
job is translating an exit code it did not produce; a stub is the only way to enumerate codes it
must translate. `update-ledger.sh`'s refusals are asserted to never reach the gate at all.

## Files and symbols

| file | change |
|---|---|
| `tests/test_harness_scripts.py` | **new.** ~10 tests, one module-level `needs_bash` fence, one sandbox helper |
| `scripts/test-count.floor` | ratcheted by the gate from 1643; committed in the same commit |
| `specs/harness-integrity/*` | this feature's spec/research/plan/impact-map/tasks |

No existing file is edited. `tests/` is not on the guard's protected list — only
`tests/golden/**` and `tests/fixtures/**` are (`guard-pretooluse.sh:124-125`) — so
**`.codystem-allow-self-edit` is not needed** and must not be created.

## Tests, each mapped to one criterion

| test (exact pytest name) | AC |
|---|---|
| `test_the_ledger_flipper_refuses_fewer_than_three_arguments` | AC1 |
| `test_the_ledger_flipper_refuses_a_feature_with_no_ledger` | AC2 |
| `test_the_ledger_flipper_refuses_a_task_id_outside_the_allowed_set` | AC3 |
| `test_the_ledger_flipper_refuses_a_citation_that_is_not_a_plain_test_name` | AC4 |
| `test_the_ledger_flipper_refuses_a_task_id_with_no_row` | AC5 |
| `test_the_ledger_flipper_does_not_prefix_match_a_longer_task_id` | AC6 |
| `test_the_ledger_flipper_short_circuits_a_row_already_marked_done` | AC7 |
| `test_no_refusal_path_reaches_the_gate` | AC8 |
| `test_the_stop_hook_maps_every_gate_exit_code` (parametrised 0,1,2,3,4,5,9) | AC9–AC15 |
| `test_the_stop_hook_lets_go_when_it_is_already_active` | AC16 |

Parametrisation is safe to cite: `update-ledger.sh:89-91` matches
`name="<cite>(\[…\])?"` precisely so a parametrised test can be named in a row.

## Risks

- **D-189 env leak (`DECISIONS.md:9753-9760`).** A subprocess harness on Windows leaked gate env
  vars into the suite's own gate-invoking tests and produced a false FAIL. Mitigation: pass an
  explicit `env=` to every `subprocess.run`, derived from `os.environ` by copy, and never mutate
  `os.environ` in-process. Do not clear `HAWEDIT_GATE_DEPTH` anywhere — clearing it is what would
  let a nested real gate start.
- **Bash resolution on Windows.** `subprocess` can find WSL's `bash.exe`, which cannot open a
  `C:/…` path (D-120). Mitigation: reuse the resolved-`bash` + POSIX-path approach already
  working at `tests/test_supply_chain.py:26-34`.
- **The floor moves.** Adding ~10 tests raises the collected count above 1643. The gate ratchets
  `scripts/test-count.floor`; `.github/workflows/gate.yml:126-127` fails any run that ratcheted
  it. Mitigation: commit the ratcheted floor in the same commit as the tests. This is the exact
  sequencing D-198 deferred the work for.
- **No local shellcheck** (D-162, `DECISIONS.md:8341`) — shell mistakes surface only on CI.
- **Concurrent session.** BLOCKED #12:596-600 recommends one session at a time or a worktree
  each. The sandbox design removes the shared-state hazard for *these* tests but not for the
  gate run itself.

## Divergence and dependencies

- **No BLUEPRINT divergence.** Grepped BLUEPRINT.md for `ledger|CODYSTEM|specs/|tasks.md|verify.sh`
  — zero hits; the enforcement harness is outside the frozen spec (`specs/constitution.md:25-26`).
  No freeze-waiver ADR owed.
- **No new runtime dependency**, so no licence to audit and no D-002 NonCommercial question.
- **One ADR is owed on completion, not before:** D-198 `DECISIONS.md:10265-10272` left this as
  "separate work" on the record. A short `## D-NNN` closing that thread — what was tested, what
  remains structurally untestable and why, and the floor movement — is the repo's own convention
  for not leaving a deferral dangling. Recommend writing it as the last step; it is not a
  precondition for the code.

## What this deliberately does not claim

Passing these tests means the two scripts refuse what they say they refuse and translate the
codes they say they translate. It does **not** mean the ledger flipper's flip works — that half
is unreachable from pytest, and the only honest proof is running the real script by hand against
this feature's own `tasks.md`, which is in the Definition of Done and would be the first time
`scripts/update-ledger.sh` has ever executed successfully in this repository.

Approved-by: Hawa — approved in chat 2026-08-12. This line was filled in by the agent on that
instruction, not typed by the approver; recorded that way so the provenance of the approval is
not overstated.
