# Evidence-bound release-owner approval

**Measured:** 2026-08-17 on Windows, CPython 3.12, before the canonical whole-repository gate for
this unit. **Status:** code-complete handoff mechanism; owner authorization remains unset.

`src/hawedit/release_approval.py` is a two-phase boundary around the existing schema-5 release and
hosted workflow. Preparation independently requires:

- one clean `main` checkout at the provenance SHA and exact `[project]` name/version;
- exactly the wheel, SPDX JSON, provenance and `SHA256SUMS`, with no linked or extra entries;
- agreement among checksum rows, wheel METADATA and provenance identity;
- the official successful `workflow_run` plus exactly the five required successful jobs;
- strict `gh attestation verify` policy for every payload, canonicalized before evidence hashing;
- current `BLOCKED.md`, `PROGRESS.md` and forward-only rollback evidence hashes.

The four-file approval packet is deterministic and write-once. Its owner template leaves the
principal, action, timestamp, rationale and all risk acknowledgements JSON `null`. Verification
recomputes every input, requires the instruction/template/tag-command bytes to remain exact, and
accepts only canonical OpenSSH armor verified under namespace `hawedit-release-approval`. It returns
commands but has no tag, push or publish operation.

Focused adversarial verification at this checkpoint: **15 passed**, covering linked/tampered/extra
bundle entries, wrong hosted identity, missing jobs, failed attestations, equivalent-JSON
determinism, overwrite refusal, exact signed approval, incomplete risks, signature/bundle drift and
modified human-facing packet files. The installed-wheel command and hosted smoke are part of the
canonical gate/release workflow contract and still require the subsequent clean commit and hosted
run before this evidence is accepted.

The remaining action is intentionally non-automatable: the owner must review the exact packet and
sign either `approve_exact_tag` or `reject_release`. No production tag or release is asserted here.
