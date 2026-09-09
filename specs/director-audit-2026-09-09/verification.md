# Audit verification record

Date: 2026-09-09. Source: `7f499f53560b94c398c8c4d526e1c44e37ca4f5e`.

## Canonical gate

The unchanged `scripts/verify.sh` was run from the primary checkout. No commands, tests, fixtures, dependency locks or enforcement code were edited.

1. `bash scripts/verify.sh`: the Windows `bash.exe` resolved to WSL. Preflight refused a missing derived host-lock path whose Python-generated identity contained a CR. This attempt did not reach tests. Exact output: `gate.log`.
2. `C:/Program Files/Git/bin/bash.exe scripts/verify.sh`: the same script under the installed native Git Bash passed lint, strict typecheck and formatting, then ran the full test command. Final result: **3,670 passed, 1 failed, 3 errors, 1 warning**, in 884.31 seconds, as reported by pytest on this host. Exact output: `gate-git-bash.log`.

**All four non-passing cases are release-build tests refusing the dirty checkout created by this audit's untracked evidence files.** They are not evidence of an application regression or a clean-baseline failure. The refusal names the new screenshots, probes and gate logs. A clean-source gate was not rerun; no source commit was made merely to satisfy the release test. This is not a green gate or feature-acceptance claim. Tests were not filtered, deselected, disabled or modified.

Affected tests:

- `tests/test_build.py::test_the_wheel_contains_every_file_the_audit_report_says_it_does` — failure.
- `tests/test_build.py::test_two_builds_of_one_commit_are_byte_identical` — fixture error.
- `tests/test_build.py::test_every_entry_carries_the_commits_timestamp_not_the_clock` — fixture error.
- `tests/test_build.py::test_build_script_reports_the_hash_locked_private_builder` — fixture error.

The suite-generated JUnit report was read, not manually changed. The editorial rating does not use these audit-induced build refusals as negative product evidence.

## Hosted checks

`gh api repos/HawzhinBlanca/HawEdit/commits/7f499f53560b94c398c8c4d526e1c44e37ca4f5e/check-runs` returned HTTP 422, “No commit found for SHA.” This does not establish current hosted checks. No commit was pushed and no CI run was requested during the audit.

## Other fresh checks

- Five browser screenshots saved, reopened and inspected; no-source completion and duplicate media URLs reproduced against the running local application. Server and browser tab created for the audit were closed afterward.
- Critic/condensation/narrative probes recorded in `behavior-probes.json`; reproduction instructions in `probes.md`.
- Three current MP4s hashed and probed, then sampled freshly; exact paths, hashes, formats and sample times in `media-inspection.json`.
- Canonical transcript context for selected and neighboring sentences saved in `selected-source-context.json`.
- Eleven inspected source/custom-producer files bound by hashes, with parsed function lines, in `source-evidence-manifest.json`.
- All embedded report images were found on disk. No new movie, claim of full audio review, new human judgment, or model benchmark was created.

Environment: Windows 11 build 26200, Python 3.12.10, FFmpeg/FFprobe 8.1.1 full Gyan build. These versions describe audit probes/media inspection, not a speed or quality benchmark. A contemporaneous report from another tool appeared under a separate specifications path and was preserved.
