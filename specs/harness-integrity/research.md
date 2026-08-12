# harness-integrity — research

Grounding caveat: Serena is not connected in this session, so no claim below came from
`find_symbol` / `find_referencing_symbols`. Everything is ripgrep + full reads, cited file:line.
AGENTS.md's grounding rule asks for Serena; this is a substitution, declared rather than hidden.

## What this answers to
- **No BLUEPRINT §.** Grepped BLUEPRINT.md for `ledger|CODYSTEM|specs/|tasks.md|verify.sh` — zero
  hits. §8 is the *accuracy* harness (BLUEPRINT.md:409), not the enforcement one. Per
  `specs/constitution.md:25-26` this implements no § and diverges from none, so **no ADR is owed
  for the freeze**.
- **D-198 (DECISIONS.md:10209) is the parent.** DECISIONS.md:10265-10272 states the pytest test was
  omitted *deliberately* "so `scripts/test-count.floor` stays untouched … left as separate work."
  This feature is that work. Nobody decided these scripts should stay untested.
- **BLOCKED #12** (BLOCKED.md:522, live) — two sessions share this checkout. Confirmed live today:
  a second session pushed `ff77942` to main mid-session. BLOCKED.md:557 records that two sessions
  running the gate in one tree produce garbage results.

## Files and symbols
- `scripts/update-ledger.sh` (123 lines). Refusals **before** the gate: usage :28-32, missing
  ledger :41-44, task id not `[A-Za-z0-9_.-]+` :49-52, cited test not a plain name :59-65, no row
  :67-70, already-done short circuit :72-75. Then `bash scripts/verify.sh` at **:78**. After it:
  report exists :84-87, citation regex `name="cite(\[…\])?"` :88-97, awk flip :102-113, provenance
  append to `specs/<f>/ledger.log` :117-119.
- `scripts/claude-stop-verify.sh` (67 lines). Whole contract is the exit-code map at :44-67 —
  0→0, 2→1, 4→1, everything else→2 — plus the `stop_hook_active` short circuit :37-39.
- `src/hawedit/gate.py` — already covered by `tests/test_gate.py`, `tests/test_gate_evidence.py`.
- `scripts/guard-pretooluse.sh` — covered by `scripts/guard-test.sh` (56 checks), run by
  `.github/workflows/gate.yml:42`, **not** by `verify.sh`.
- Precedent for bash-from-pytest: `tests/test_supply_chain.py:26-28` (`needs_bash`, subprocess,
  POSIX paths per D-120) and `tests/test_build.py:30-34` (`needs_build` = bash + git).

## Current behavior
`scripts/update-ledger.sh` has **never executed**. `find specs -type f` returns only
`specs/constitution.md`; its target `specs/<feature>/tasks.md` (:38) has never existed, and :41-44
refuses without one. So AGENTS.md's "only `update-ledger.sh` flips a row" is currently vacuous —
PROGRESS.md's 33 DONE rows were flipped some other way. These are **two different ledgers**:
PROGRESS.md holds §9 milestone tables (`| Task | Definition of Done | Status | Evidence |`,
PROGRESS.md:70-71); `specs/<f>/tasks.md` holds checkbox rows `- [ ] T1 …`. `specs/` and `tasks.md`
appear nowhere in PROGRESS.md.

## Integration points / callers to keep working
- `.claude/settings.json` wires `claude-stop-verify.sh` on Stop. Nothing calls `update-ledger.sh`
  programmatically — it is human/agent-invoked only. No src caller of either. No import graph to break.
- New files under `tests/` are **not** on the guard's protected list (only `tests/golden/**` and
  `tests/fixtures/**` are), so adding tests needs no `.codystem-allow-self-edit`. Editing either
  script would.

## Risks
- **The post-gate half of `update-ledger.sh` is unreachable from pytest.** Reaching :88 needs
  `verify.sh` to exit 0 at :78, but pytest is itself running *under* verify.sh, and verify.sh
  refuses nested invocation with exit 4. The citation check, the awk flip and the provenance line
  cannot be covered this way; that limit must be recorded, not papered over
  (precedent: `evidence/two-builds-of-one-commit.md:49` records an accepted untested refusal).
- **D-189 (DECISIONS.md:9753-9760):** a subprocess harness doing this on Windows leaked env into
  the suite's own gate-invoking tests and reported a **false FAIL**. Tests must not export gate
  env vars into an inherited environment.
- **D-092 :3725-3730 / D-093 :3786:** the gate must resolve its tools under `sys.prefix`; faking
  `pytest` or `PY` is the attack those ADRs closed. A stub gate is legitimate *only* for the Stop
  wrapper, whose entire job is translating an exit code — D-198:10263 used exactly that.
- **The floor moves.** `scripts/test-count.floor` is 1643 and the gate ratchets it; CI fails a run
  that ratcheted it (`.github/workflows/gate.yml:126-127`), so the new floor must be committed in
  the same commit as the tests.
- **Shared `.gate/` under BLOCKED #12.** `verify.sh` deletes and rewrites `.gate/last-test-run.xml`;
  a concurrent session running the gate corrupts both runs.
- No shellcheck locally — D-162 (:8341) put it in CI only, so a shell mistake surfaces on the runner.
