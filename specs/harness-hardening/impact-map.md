# harness-hardening — impact map

Grounding caveat: callers found with ripgrep, not `find_referencing_symbols`.

## Symbols and files to be touched

| task | file | change | callers |
|---|---|---|---|
| T1 | `.github/workflows/gate.yml:81-90`, `:96-103` | add `set -o pipefail` + `rc` capture | GitHub Actions only; no code calls it |
| T2 | `scripts/verify.sh:69-72` | add `PYTEST_ADDOPTS` to the refusal list | `update-ledger.sh:78`, `claude-stop-verify.sh:42`, `gate.yml:80`, PostToolUse hook (`--fast`) |
| T3 | `scripts/verify.sh:128`, `:133` and `src/hawedit/gate.py:169-194` | write and require a run token | as above, plus `gate.yml:122` which calls `gate.py` directly |
| T4 | `scripts/guard-pretooluse.sh:91-129`, `:185-196` | normalise the candidate before matching | `.claude/settings.json` PreToolUse; `scripts/guard-test.sh` |

## Every existing test that must still pass

- **T2 and T3 change `verify.sh`'s exit behaviour.** `tests/test_harness_scripts.py`'s Stop-hook
  matrix drives the wrapper against a *stub* gate, so it is unaffected by what the real gate
  decides — but `test_the_stop_hook_runs_the_wrapper_and_never_the_gate_directly` pins the wiring
  and would catch a fix that rerouted the hook.
- **T3 changes `gate.py`'s refusal set.** `tests/test_gate.py` and `tests/test_gate_evidence.py`
  are the regression suite. AC9 exists specifically because the freshness refusal is easy to
  break while adding a second one beside it.
- **T4 changes `should_block`.** `scripts/guard-test.sh`'s 56 checks are the only coverage that
  exists, and they are bash-level — `verify.sh` does not run them, `.github/workflows/gate.yml:42`
  does. A T4 regression is therefore invisible locally and red on CI, which is the wrong way
  round for the task most likely to over-block.

## Callers with no test — findings

1. **`gate.yml` has no test that its steps do what their names claim.** AC3 adds the first one,
   and only for the pipefail property. Nothing asserts the workflow's step *order*, that the gate
   step precedes the evidence step, or that the floor-diff step runs at all. Out of scope here;
   recorded because T1 touches that file and the gap is adjacent.
2. **`guard-test.sh` is not run by `verify.sh`.** So the local gate is green whether or not the
   guard works. That is a deliberate D-198 choice — the guard needs no venv, and CI runs it
   before install — but it means T4's regression signal is CI-only. Worth revisiting as its own
   task, not smuggled into this one.

## Shared mutable state

| state | touched by | mitigation |
|---|---|---|
| `.codystem-allow-self-edit` | every task | created and deleted within the task; repo-root and shared with a live second session (BLOCKED #12) |
| `.gate/last-test-run.xml` | T3 | the task changes who may write it; the concurrent-session hazard is the thing being fixed |
| `scripts/test-count.floor` | every task that adds tests | committed in the same commit (`gate.yml:126-127`) |
