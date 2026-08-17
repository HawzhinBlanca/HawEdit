# ledger-id-exactness — research

Grounding caveat: Serena is still not connected. Claims below are ripgrep + full reads + a
reproduction run, cited file:line. Declared, not hidden.

## The defect, reproduced

`scripts/update-ledger.sh` constrains the task id at `:49` to `^[A-Za-z0-9_.-]+$`, then
interpolates it unescaped into two regexes: a `grep -E` at `:67`/`:72` and an awk ERE at `:105`.
A dot is legal in that character class **and** is a regex metacharacter, so `T.` passes
validation and then matches a row it does not name.

Measured on this machine (Windows 11, Git Bash, GNU awk), against a ledger holding only
`- [ ] T1  a real row   (tests: test_one)`:

| stage | task `T.` | task `T9` (control) |
|---|---|---|
| validator `:49` | accepted | accepted |
| row check `:67` | matches the `T1` row | no match |
| awk flip `:105` | rewrites the row to `- [x] T1`, exits 0 | exits 3 |

Extraction method: `sed -n '103,111p' scripts/update-ledger.sh > flip.awk` then
`awk -v task='T.' -f flip.awk` — the script's own program text, not a retyped copy.

`-` is harmless: it is only special inside a bracket expression, and the id is never placed in
one. `T10` correctly fails to match `T1`, so the `([[:space:]]|$)` anchoring at `:67` is right.
**The dot is the only leak.**

## Why it matters more than its likelihood

The consequence is not a wrong flip alone. `:117-119` writes provenance recording
`TASK=<the argument>`, so a `T.` flip leaves `ledger.log` naming a task id that appears in no
row of the ledger it just edited. `update-ledger.sh:8-18` states the script's whole purpose as
matching "the row … exactly, within one feature's file", and `:115-116` calls the provenance
"what lets a reader tell a row the gate flipped from a row somebody typed an x into". A
divergence between the evidence and the claim is the failure class D-093 and D-157 both exist to
close.

Reachability is low — an operator must type `T.` deliberately, and the gate still runs first, so
nothing green is forged. This is a correctness hole in an exactness guarantee, not an exploit.

## Files and symbols
- `scripts/update-ledger.sh:49-52` — the validator. Dropping `.` from the class would also close
  it, but dotted ids are idiomatic here: `PROGRESS.md` numbers milestones `M0.12`, `M7.3`.
  Narrowing the alphabet trades one defect for a restriction the repo's own numbering wants.
- `scripts/update-ledger.sh:67` — `grep -qE "^- \[[ xX]\] ${task}([[:space:]]|$)"`, the gate on
  whether a row exists.
- `scripts/update-ledger.sh:72` — the already-done short circuit, same interpolation.
- `scripts/update-ledger.sh:102-112` — the awk flip, `"^- \\[ \\] " task "([ \t]|$)"`.
- `tests/test_harness_scripts.py` — 16 tests from the harness-integrity feature; `sandbox()`,
  `write_ledger()`, `gate_ran()` and `run_ledger()` are already in place and are what a
  regression test for this would reuse. `gate_ran()` is the useful one: a *legitimate* dotted id
  must still reach the gate, and the stub marker is how that is observed.

## Integration points
No caller to keep working — `update-ledger.sh` has no programmatic caller anywhere in the repo
(prose references only: `AGENTS.md:35`, `AGENTS.md:88`, the plan/implement skills,
`specs/constitution.md:15`). The only consumers of its behaviour are the 8 tests added in
`3b83897` covering its refusals.

## Risks
- **Enforcement surface.** `scripts/update-ledger.sh` is on the guard's protected list
  (`guard-pretooluse.sh`), so the edit needs `.codystem-allow-self-edit` created before and
  deleted after — AGENTS.md's stated route, which makes the self-edit visible in `git status`.
- **No local shellcheck** (D-162) — a quoting mistake in the fix surfaces only on CI.
- **The floor moves again** with any new test; it must ship in the same commit
  (`.github/workflows/gate.yml:126-127`).
- **A fix must not narrow what is legal.** `T1.2` has to keep working, and that is the
  regression the tests must hold, not an afterthought.

## Answers to
No BLUEPRINT § — the enforcement harness is outside the frozen spec (`specs/constitution.md:25-26`).
D-199 records this defect as found-and-not-fixed and says it "gets its own spec". This is it.
