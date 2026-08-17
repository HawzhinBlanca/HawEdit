---
name: plan
description: Phase 2 of the CODYSTEM loop for hawedit. Turn research.md into an approvable plan.md plus impact-map.md (callers of every symbol to be touched) and a tasks.md ledger. Stops for HUMAN approval before any code. No code is written.
---

# Plan (human gate)

**Goal:** a plan a human can check in about 30 seconds, plus a regression impact map — written
before a single line of implementation.

## Procedure

Read `specs/<feature>/research.md` and `specs/constitution.md`. Then write three files. Do NOT
write code.

**`specs/<feature>/plan.md`** — approach and rationale; the exact files and symbols to change;
the new tests, each mapped to one EARS criterion; risks. If this diverges from `BLUEPRINT.md`,
say which § and why, and note that an ADR in `DECISIONS.md` is owed. If it adds a runtime
dependency, name it, its licence, and confirm the licence is not NonCommercial (D-002 makes
that a hard reject). End with a blank line for a human:

```
Approved-by:
```

**`specs/<feature>/impact-map.md`** — for every symbol you will touch, its callers from
`find_referencing_symbols`, and the tests that cover each caller. A caller with no test is a
finding, not a footnote: write the test into the plan.

**`specs/<feature>/tasks.md`** — the ledger the gate flips. Smallest-correct-change tasks, each
citing the test names that will prove it:

```markdown
# Tasks ledger — <feature>
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [ ] T1  <smallest correct change>   (tests: test_<name>)
- [ ] T2  <next>                      (tests: test_<name>, test_<other>)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] Independent diff review vs plan.md done
```

Cite test names exactly as pytest will report them — `update-ledger.sh` looks each one up in
the JUnit report by name and refuses a citation it cannot find.

Then **stop** and wait for approval.

## Done when
- `plan.md` exists with an `Approved-by:` line left blank for a human.
- `impact-map.md` lists every symbol to be touched and its callers.
- `tasks.md` exists, every row unchecked, every row citing at least one named test.
- Each EARS criterion in `spec.md` maps to at least one planned test.
- **STOP.** Do not start `implement` until a human fills in `Approved-by:`.

→ Next (after approval): `implement`.
