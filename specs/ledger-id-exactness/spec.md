# ledger-id-exactness — acceptance criteria (EARS)

Two interpolation sites, one defect class: a value the validator permits is also a regex
metacharacter, and it is interpolated unescaped.

## The task id — `update-ledger.sh:49` validated, `:67` / `:72` / `:102` interpolated

- **AC1** WHEN the task id contains a `.`, THE ledger flipper SHALL treat that character as a
  literal and SHALL NOT match a row whose id differs from it.
- **AC2** WHEN a task id containing a `.` names a row that genuinely exists, THE ledger flipper
  SHALL match that row and proceed to the gate.
- **AC3** WHEN a task id containing a `.` matches no row literally, THE ledger flipper SHALL
  refuse with exit 2 and SHALL NOT invoke the gate.
- **AC4** WHEN a task id is already-done and contains a `.`, THE ledger flipper SHALL apply the
  already-done short circuit only to the literally matching row.

## The citation — `update-ledger.sh:60` validated, `:91` interpolated

This is the evidence check. `update-ledger.sh:11-16` gives its whole purpose: "a citation naming
a test that does not exist — or that exists and did not run — is caught here for free, against
evidence rather than against the agent's word."

- **AC5** WHEN a cited test name contains a `.`, THE ledger flipper SHALL treat that character as
  a literal when searching the JUnit report.
- **AC6** WHEN a cited test name matches no test in the report literally, THE ledger flipper
  SHALL refuse with exit 1 even if the citation would match another test as a regex.
- **AC7** WHEN a cited test name is parametrised, THE ledger flipper SHALL continue to match the
  `name="test_x[case]"` form, which the `(\[[^"]*\])?` suffix at `:91` exists to allow.

## Both

- **AC8** THE ledger flipper SHALL continue to accept `.` and `-` in a task id and in a citation,
  because the project numbers its own work `M0.12` and `M7.3`.

Narrowing the accepted alphabet at `:49` or `:60` is an explicit non-goal: it closes the defect
by forbidding ids the repository's own numbering uses.

## Reachability, stated up front

AC1–AC4 are testable from pytest — they fire above `update-ledger.sh:78`. AC5–AC7 are **not**:
the citation check runs after the gate returns 0, and pytest runs underneath that same gate,
which refuses a nested full run (D-199). They are verified by extracting the grep from the script
and running it directly, with the output recorded in the ADR. A criterion that cannot be held by
the suite is written down as such rather than quietly dropped.
