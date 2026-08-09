# Exact-SHA release gate evidence — 2026-08-09

## Finding

`hawedit-release` checked only that Git `HEAD` was clean and stable. Its own positive test created a
brand-new repository with no remote, workflow, gate script or test evidence and successfully
published a wheel. Therefore a clean commit with a failing test—or no tests at all—could receive
valid schema-3 provenance and a write-once release directory.

Local `.gate/last-test-run.xml` is not a safe repair: it is ignored, mutable and carries no commit
SHA. Automatically selecting the latest remote run is also ambiguous under concurrent pushes.

## Enforced policy

Publication now requires an explicit `gate_run_id` / `--gate-run-id`. Before a builder or output
directory is created, HawEdit queries the GitHub API and requires all of the following:

- repository and head repository are exactly `HawzhinBlanca/HawEdit`;
- workflow path is exactly `.github/workflows/gate.yml`;
- event is `push`, branch is `main`, and `head_sha` equals the clean release `HEAD`;
- run and its single `gate` job are completed successfully and share the same attempt/SHA;
- the returned job set is complete rather than silently paginated;
- all eight mandatory install, full-gate, real-render, real-ingest, runner and evidence steps
  completed successfully; and
- provenance run/job links are constructed from the verified official ids.

Missing IDs, API/network errors, forks, manual/PR/feature runs, wrong revisions, incomplete or
failed jobs, skipped/missing steps and malformed evidence are release refusals. `GITHUB_TOKEN` is
optional for public API access and is sent only in the authorization header. The exact accepted
run, attempt, job, completion time and URLs are recorded in deterministic schema-4 provenance.
Redirect responses are not followed, preventing the authorization header from crossing hosts.

Both builds read two separate pristine exports produced by
`git --no-replace-objects archive <verified revision>`. They never build from the live worktree,
and build 2 cannot observe files a backend generated in build 1's source directory. The final
worktree check remains an operator-safety refusal, not the artifact's source-of-truth mechanism.
Extraction uses a version-independent path-confined regular-file implementation, refuses
traversal, backslash ambiguity, links and special members, and therefore works across the declared
Python 3.11.0+ range rather than silently requiring 3.11.4's tar filter.

## Verification

- Focused Ruff and format checks: clean.
- Focused mypy: clean.
- `tests/test_release.py`: 32 tests on both Python 3.11.15 and 3.12.13 cover the successful
  publication/provenance path, missing ID, 18
  independent evidence mutations, incomplete pagination, API failure, cross-host redirect token
  isolation, pre-builder refusal, live-worktree TOCTOU, independent source roots and write-once
  behavior, plus hostile archive traversal/link refusal.
- Canonical host-extras (`dev,media,cloud,gpu`) gate: `1282 passed, 0 skipped`; Ruff, format and mypy clean across 100
  source files; `VERIFY OK`.
- Live positive control: official `main` push run `31295014063` was accepted for exact SHA
  `b34d88dc734f8aefd6c7c7d10ff6953cc5e24e92`.
- Live negative control: successful run `31294726370` was refused for exact SHA `c983673...`
  because it was a manual feature-branch run, not the production `main` push.

This binds publication to GitHub's canonical recorded gate result. It does not cryptographically
sign the release or replace the still-open signing/authenticity work.
