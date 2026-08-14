# harness-integrity — impact map

Grounding caveat: Serena is not connected in this session, so callers below were found with
ripgrep over the whole repo rather than `find_referencing_symbols`. Stated, not hidden.

## Production symbols changed: none

This feature adds one test file. No function, class, or script under `src/` or `scripts/` is
edited, so there is no signature to break and no caller to keep working. The table below is the
inverse of the usual one: it lists the callers of the things being *tested*, to show that
testing them cannot disturb them.

## The things under test, and who calls them

| under test | callers found | test covering that caller today |
|---|---|---|
| `scripts/update-ledger.sh` | **No programmatic caller anywhere.** `grep -rn "update-ledger" --include=* .` outside its own file and docs: `AGENTS.md:35`, `AGENTS.md:88`, `.claude/skills/implement/SKILL.md`, `.claude/skills/plan/SKILL.md`, `specs/constitution.md:15`. All prose. Invoked by a human or an agent, never by code. | none — this feature adds the first |
| `scripts/claude-stop-verify.sh` | `.claude/settings.json` Stop hook wiring. One caller, and it is configuration, not code. | none — this feature adds the first |
| `scripts/verify.sh` | called by `update-ledger.sh:78`, `claude-stop-verify.sh:42`, `.github/workflows/gate.yml:80`, and the PostToolUse hook (`--fast`) | `tests/test_gate.py`, `tests/test_gate_evidence.py` cover `hawedit.gate`, the program verify.sh grades with; verify.sh's own step order is not under test |
| `scripts/test-count.floor` | read by `src/hawedit/gate.py`, ratcheted by it, and diffed by `.github/workflows/gate.yml:127` | `tests/test_gate.py` (floor semantics), `gate.yml:126-127` (must-not-ratchet-in-CI) |

## Callers with no test — findings, not footnotes

1. **`.claude/settings.json` → `claude-stop-verify.sh` is wired by configuration nothing checks.**
   No test asserts that the Stop hook is actually registered, or registered to the right script.
   A typo in that JSON silently disables the Stop gate and every run stays green.
   **Decision: out of scope for this feature, recorded here.** The tests planned cover the
   script's behaviour; they cannot cover whether Claude Code is configured to call it. That is a
   different kind of assertion (parse `.claude/settings.json`, assert the hook path exists and is
   executable) and it belongs in its own task with its own row, not smuggled into this one.
   Worth raising as the next candidate after this feature.

2. **`verify.sh`'s own step ordering has no test.** `tests/test_gate.py` covers `gate.py`, which
   grades the report; nothing asserts verify.sh runs lint → typecheck → format → pytest → grade
   in that order, or that `--fast` stops after typecheck. Out of scope here; noted because the
   impact map is the right place to say a gap was seen and left.

## Shared mutable state touched

| state | by this feature | mitigation |
|---|---|---|
| `.gate/last-test-run.xml` | **not touched** — every test runs against a stub gate in `tmp_path` | sandbox design, plan.md §Approach |
| `scripts/test-count.floor` | ratcheted 1643 → new count, once, by the gate | committed in the same commit (`gate.yml:126-127`) |
| `os.environ` / `HAWEDIT_GATE_DEPTH` | **not mutated in-process** | explicit `env=` copy per `subprocess.run` (D-189, `DECISIONS.md:9753-9760`) |
| working tree | one new file under `tests/`, plus `specs/harness-integrity/` | neither path is guard-protected (`guard-pretooluse.sh:124-125`) |
