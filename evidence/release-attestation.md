# Exact-SHA release attestation design — 2026-08-09

## The gap

`hawedit-release` produced a byte-reproducible wheel, deterministic SPDX SBOM, schema-5
provenance and `SHA256SUMS`, all bound to an exact successful canonical gate. Those files still
authenticated only one another. A party able to replace the bundle could rebuild the wheel,
rewrite its self-asserted metadata and publish a new checksum manifest with no external trust root.

## Promotion boundary

`.github/workflows/release.yml` is a `workflow_run` consumer of `gate`. Its build and attestation
boundaries are refused unless the completed run:

- is in `HawzhinBlanca/HawEdit` and its head repository is also that exact repository;
- was a `push` to `main`; and
- has `workflow_run.head_sha` equal to this release run's own default-branch `github.sha`; and
- concluded successfully.

The SHA equality is deliberate. GitHub defines `GITHUB_SHA` for a `workflow_run` as the current
default-branch commit, and `actions/attest` places that OIDC claim into its standard provenance. If
`main` advances from `S` to `T` before `S` is promoted, the workflow refuses stale `S` instead of
signing bytes built from `S` with a predicate that names `T`.

The unprivileged build job checks out `workflow_run.head_sha`, with persisted Git credentials
disabled. It has only `contents: read` plus the `actions: read` needed to query the triggering run
and jobs, and runs the existing release command with `workflow_run.id`. That command independently
queries the GitHub API and fails closed unless
repository, workflow path, event, branch, SHA, job and every mandatory gate step are the expected
completed success. It exports that verified Git object twice and publishes only equal wheels. The
job uploads four explicit paths as a one-day transport artifact; it has no write permission and
cannot mint an OIDC token or write an attestation.

A dependent zero-permission matrix starts on fresh Python 3.11 and 3.12 runners with no checkout.
Each leg downloads the exact transport, installs the one wheel into a clean venv with binary-only
dependencies, runs `pip check`, resolves all installed font/model metadata paths from outside the
checkout, and starts all six console entry points. Attestation needs every matrix leg.

The final dependent job starts on another fresh runner and does not check out or execute repository code.
`actions/download-artifact` validates the transport digest. Trusted workflow shell then refuses
anything except one regular wheel, its one regular SPDX document, `release-provenance.json` and
`SHA256SUMS`: nested, linked, special, extra, missing, malformed-manifest or digest-mismatched
entries all fail. It opens the wheel independently, requires exactly one METADATA member,
requires the normalized distribution to be `hawedit`, and requires its name/version to match the
PEP 427 filename. It then binds schema-5 distribution/version plus
repository/workflow/event/branch/run/SHA/wheel/SBOM fields to the triggering event and measured
bytes. Only this isolated job has `contents: read`,
`id-token: write` and `attestations: write`. It uses GitHub OIDC through `actions/attest` to create
build-provenance attestations for the exact same explicit four paths that the final upload action
receives. Repository code therefore never receives attestation authority, and un-attested
descendants cannot enter `hawedit-release-<exact SHA>`.

All remote actions are immutable full commits resolved from their official release tags:

| Action | Release | Commit |
|---|---:|---|
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/setup-python` | v7.0.0 | `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| `actions/attest` | v4.1.1 | `a1948c3f048ba23858d222213b7c278aabede763` |
| `actions/download-artifact` | v8.0.1 | `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` |
| `actions/upload-artifact` | v7.0.1 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` |

## Local verification

- `tests/test_release_workflow.py` pins the trigger, official-repository/main-push conditions,
  permission split, clean 3.11/3.12 installed-wheel matrix, fresh privileged job, exact-SHA
  checkout, release-run binding, exact-set, wheel-identity and manifest/provenance checks, action commits, equal
  attestation/upload path lists and step order.
- `tests/test_release.py` continues to exercise the exact-gate verifier and real double build.
- `tests/test_fetch_scripts.py` rejects every remote workflow action not pinned to 40 hex digits.
- PyYAML 6.0.3 parsed the workflow.
- The official `actionlint` v1.7.12 Windows archive was verified against its release checksum;
  `release.yml` returned zero findings, and the combined release/gate run returned zero after the
  one declared custom self-hosted label `hawedit-gpu` was ignored explicitly.

The local workflow/security set passed, and actionlint accepted the edited release workflow. The combined
canonical gate then passed 1,823/1,823 with zero skips; Ruff, format, Mypy and fresh JUnit evidence
passed. Fresh local Python 3.11.15 and 3.12.13 venvs also installed and executed the exact same
edited-tree wheel contract; see `evidence/python-support.md`.

## Required live acceptance after merge

This branch cannot manufacture the missing hosted proof: GitHub loads a `workflow_run` consumer
from the default branch. Do not call authenticity complete until all of these are observed on a
post-merge protected-`main` push:

1. the Python 3.12 prerequisite and canonical `gate` succeed for SHA `S`;
2. `release` starts from that exact run, both installed-wheel matrix legs succeed, and the
   attestation job uses the same `S`;
3. the uploaded `hawedit-release-S` contains exactly four non-empty files and its
   `SHA256SUMS` verifies; and
4. each downloaded file passes:

   ```bash
   EXPECTED_SHA=THE_EXACT_40_HEX_GATED_SHA
   gh attestation verify PATH/TO/FILE \
     --repo HawzhinBlanca/HawEdit \
     --signer-workflow HawzhinBlanca/HawEdit/.github/workflows/release.yml \
     --source-ref refs/heads/main \
     --source-digest "$EXPECTED_SHA" \
     --signer-digest "$EXPECTED_SHA" \
     --deny-self-hosted-runners
   ```

`--repo` alone is intentionally insufficient: another workflow in the same repository is a
different signer policy. These flags require the exact release workflow, source ref, source SHA,
workflow-definition SHA and GitHub-hosted runner. The attestation then proves the GitHub Actions
identity and workflow provenance of those exact bytes. It does **not** create a version/tag policy,
a durable GitHub Release, a transitive runtime hash lock, or evidence that real
deployment/model/benchmark gates passed. Those remain separate work.
