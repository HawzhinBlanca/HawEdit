# Research — integrate the production branch

Date: 2026-08-25

## Authority and context

- Owner instruction: commit, push, and merge only when fully green, with professional Git hygiene.
- Vault canon: `Gates/branch-protection.md` requires protected `main`, including administrators.
- Vault decision: `Decisions/HawEdit Agentic Branch Status.md` records that PR #22 was merged with a
  merge commit so its per-commit evidence remained intact. It also warns that the WSL-ASR VEX review
  date must not be advanced merely because the source digest changes.
- Repository authority: `AGENTS.md` and `scripts/verify.sh` define the canonical local gate.

Serena is not available in this tool session. Git's merge-tree and `rg` caller mapping were used as
the read-only substitute before any source edit.

## Exact branch state

- Integration branch: `codex/visual-short-window-provenance`
- Local head before integration: `84d214fc39f74f60564bd10ef3fd7134e97ec3ee`
- Remote branch head: `7983ca077b76f129d5bdfc09cb915711b9fa820a`
- Current `origin/main`: `0f9179dc568546bdedb018be1722d344db80e50f`
- Merge base: `4dbffa2585e50e60d4dcebf6c508699aac0a35ad`
- Divergence: 44 commits on current main and 30 commits on the integration branch after the base.
- PR #21 is open, draft, mergeable state `CONFLICTING`, with its last remote checks green for the
  older remote head.
- The working tree is clean. Three local commits are not yet pushed: agent configuration files,
  Stage 6 delivery corrections, and the resulting test-floor ratchet.

## Predicted conflicts

`git merge-tree --write-tree --messages HEAD origin/main` reports six textual conflicts:

1. `AUDIT_REPORT.md`
2. `DECISIONS.md`
3. `pyproject.toml`
4. `scripts/test-count.floor`
5. `security/wsl-asr-vex.json`
6. `src/hawedit/pipeline.py`

Other overlapping files auto-merge, including `PROGRESS.md`, `README.md`, `judge.py`, and their
tests. Those auto-merges still require semantic review and full-suite verification.

## Semantic merge requirements

- Preserve the branch's Stage 6 caption timing, face tracking, NVENC quality, loudness, duration,
  dead-air and QC behavior.
- Preserve main's durable/agentic workflow, escalation, proposal, artifact inspection, injection
  guards, and report sanitisation.
- Compose both console-script sets and the `agentic` optional dependency; do not choose one side of
  `pyproject.toml` wholesale.
- Preserve both decision and audit histories. Historical evidence may not disappear to simplify a
  conflict.
- Resolve the floor to the accepted main value, then let the canonical gate ratchet it from the
  combined suite; do not invent a combined count.
- Recompute the WSL-ASR applicability source digest from the merged source. Keep the existing review
  date and expiry unless the twelve vulnerability dispositions receive a separate real review.
- Keep every conflict resolution attributable in one merge commit. Do not rebase, squash, force
  push, or broadly stage unrelated paths.

## Verification and promotion requirements

1. No conflict markers or unmerged entries.
2. `git diff --check` clean.
3. Canonical `bash scripts/verify.sh` succeeds from the committed merge tree.
4. Any automatic floor ratchet is committed explicitly with the visible self-edit marker protocol.
5. Push normally, make PR #21 ready, and require hosted checks for the exact pushed SHA.
6. Merge through protected GitHub `main` with a merge commit only after all required checks succeed.
7. Verify the resulting main SHA, PR merge metadata, remote branch state, and clean local worktree.
8. Capture the milestone in the central Obsidian vault with source SHAs and CI run IDs.
