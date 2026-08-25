# Plan — integrate and merge the production branch

Research: `specs/integrate-production-branch/research.md`

Specification: `specs/integrate-production-branch/spec.md`

Impact map: `specs/integrate-production-branch/impact-map.md`

Approved-by: Hawa — 2026-08-25 ("commit push and merge when green fully get pro git hygiene")

1. Create the visible self-edit marker because the merge touches the canonical test floor.
2. Merge `origin/main` into the current branch with `--no-commit --no-ff` so every conflict is
   reviewed before one integration commit is created.
3. Resolve the six predicted conflicts by semantic composition, not whole-file side selection except
   the pre-merge accepted floor, which starts from main and is subsequently owned by the gate.
4. Review every auto-merged overlapping file and run focused tests for pipeline, durable workflow,
   proposals, agents, captions, reframing, rendering, release metadata, VEX and claims.
5. Recompute the exact merged-source VEX digest without advancing the vulnerability review facts.
6. Run formatting/lint/type checks, conflict-marker scans and `git diff --check`.
7. Commit the merge with explicit evidence in the message. Remove the self-edit marker.
8. Run the exact canonical full gate on the committed merge tree. If it ratchets the floor, use the
   visible self-edit protocol, commit that one path explicitly, and rerun the canonical gate.
9. Push normally. Mark PR #21 ready and wait for all required exact-SHA checks.
10. Merge PR #21 through protected `main` using a merge commit. Never force, squash or bypass hooks.
11. Verify the PR merge SHA, required checks, remote branch disposition and local cleanliness.
12. Capture the completed integration milestone in the Obsidian vault with provenance and any VEX
    expiry warning.
