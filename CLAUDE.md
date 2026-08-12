# CLAUDE.md

This file is the Claude Code bridge to the single source of truth, `AGENTS.md`.
AGENTS.md is the de-facto open standard (read natively by Codex/Copilot/Gemini too),
so all operating rules live there and are imported here.

@AGENTS.md

## Claude-only notes
- **MCP servers:** configured in `.mcp.json`. Serena provides the symbolic tools the grounding
  rules require (`find_symbol`, `find_referencing_symbols`) and needs `uvx` on PATH.
- **Hooks:** `.claude/settings.json` wires PreToolUse (`scripts/guard-pretooluse.sh`),
  PostToolUse (`verify.sh --fast`), and Stop (`scripts/claude-stop-verify.sh`). These are
  deterministic guardrails — do not attempt to bypass them.
- **Skills:** `.claude/skills/{research,plan,implement}` encode the Research → Plan → Implement
  loop. Invoke them in order; the PLAN step stops for human approval.

### Things worth knowing before the hooks surprise you
- Hooks shell out to `bash`. On Windows that means Git Bash or WSL must be on PATH, or all
  three silently degrade to warnings.
- The Stop hook runs the **full** gate, including the test suite. That is the point, and it is
  not fast. `verify.sh --fast` on PostToolUse is the quick loop.
- The PreToolUse guard reads its payload with `jq` if present and falls back to the Python that
  is already a prerequisite of this project. If neither exists it warns loudly on stderr and
  allows the call — a guard that cannot start must say so rather than look like protection.
- A blocked enforcement-file edit is not a wall: create `.codystem-allow-self-edit`, make the
  change, delete the sentinel. It exists to make harness self-edits visible in `git status`,
  not to prevent them.
- The real gate is `.github/workflows/gate.yml` on a clean runner. Nothing edited locally can
  fake it, which is why the local hooks can afford to be helpful rather than airtight.
