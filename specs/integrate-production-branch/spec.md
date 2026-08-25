# Specification — integrate the production branch

## Acceptance criteria

- WHEN current `origin/main` is integrated, THE repository SHALL preserve both the Stage 6 delivery
  corrections and main's durable/agentic workflow behavior.
- WHEN console scripts and dependency extras conflict, THE merged package metadata SHALL expose the
  union of the independently supported commands and dependencies.
- WHEN historical decision or audit documents conflict, THE merge SHALL preserve both histories and
  SHALL NOT silently discard either side's evidence.
- WHEN the WSL-ASR source identity changes, THE merged policy SHALL bind the exact merged-source
  digest without falsely changing the prior human review date.
- WHEN the combined test suite changes the passing-test count, THE canonical gate SHALL calculate
  the new floor; an agent SHALL NOT guess or hand-author it.
- WHEN the branch is pushed, THE pull request SHALL remain unmerged until every required check for
  the exact head SHA succeeds.
- WHEN PR #21 is merged, THE merge SHALL use a merge commit, SHALL preserve its commit history, and
  SHALL pass protected-main enforcement.
- WHEN integration finishes, THE local worktree SHALL be clean and the vault milestone SHALL name
  the branch head, merge SHA, gate results, CI run, and any remaining operational warning.
