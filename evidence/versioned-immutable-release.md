# Versioned immutable GitHub Release policy — 2026-08-15

## Decision

HawEdit production releases use a strict `vMAJOR.MINOR.PATCH` tag derived exactly from the
`[project].version` in the built wheel and its schema-5 provenance. The tag is an explicit release
intent and must already point to the exact accepted main SHA before publication. The release
workflow never creates a tag, never guesses a revision, and never publishes a prerelease or a
non-SemVer version.

The repository's **immutable releases** setting was enabled through the official GitHub API on
2026-08-15. The measured response was:

```json
{"enabled":true,"enforced_by_owner":false}
```

GitHub documents that a published immutable release locks its associated tag and assets. HawEdit
adds its own fail-closed boundary before that platform control:

1. the exact protected-main `gate` push must succeed;
2. fresh Python 3.11 and 3.12 jobs must install and execute the wheel outside a checkout;
3. a fresh no-checkout OIDC job must independently verify and attest the exact four payloads;
4. a separate no-checkout publish job verifies those attestations with the exact workflow,
   `refs/heads/main`, source digest, signer digest, and hosted-runner policy;
5. the strict version tag must already point to that exact accepted SHA;
6. a draft receives exactly the four verified payloads and its downloaded bytes must compare
   equal before the draft is published; and
7. the published release must report `isImmutable=true` and the exact tag, target, and asset set.

No tag means no public release. The attested Actions artifact remains available for inspection.
If a tag is intentionally created after the original release workflow completed, rerun that exact
workflow with `gh run rerun RELEASE_RUN_ID`; its immutable `workflow_run` event still binds the
same accepted gate run and SHA.

## Non-overwrite and rollback

Release automation uses no clobber, upload-to-existing, delete, tag-create, or tag-move path. An
existing draft is refused for human inspection. An existing public release is accepted only after
its tag, accepted SHA, immutable state, exact four downloaded bytes, checksums, and attestations
all verify; no mutation is made.

Operators must never move, delete, or reuse a production release tag. Rollback is forward-only:
publish a new patch version containing the corrective or reverted source, keep the prior release
available for audit, and document the superseded version in the new release notes. A compromised
credential or artifact is an incident, not permission to rewrite release history.

## Intended first version

The current project version is `0.1.0`, so its only valid production tag is `v0.1.0`. That tag has
not been created. Publication remains intentionally blocked until the accepted main gate, hosted
WSL job, real product-path evidence, and required owner acceptance are complete.

## Automated evidence

- `tests/test_release_workflow.py` binds the fourth job's trigger, permissions, no-checkout
  boundary, exact tag resolution (including one-level annotated tags), draft-first order,
  attestation policy, no-clobber behavior, immutable-state check, byte-for-byte idempotence, and
  action pins.
- PyYAML parsed the four-job workflow and the embedded publish shell passed `bash -n` on this edit.
- The focused workflow suite passed 15/15 before the documentation contract was added.

Live acceptance still requires the exact tag, hosted release run, published URL, downloaded
payload verification, and `gh attestation verify` output. This document defines the policy; it
does not fabricate those results.
