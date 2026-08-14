# Main delivery-audit semantic merge — 2026-08-10

## Identities

- Readiness first parent: `e8a411edd2da296dec4a2f6f87f8dbfce7fc9e3b`
- Protected-main second parent: `5eba372931eb6aa97edfca70cce6fbcc0718d8e3`
- Merge: `5a9099abe6d2ff7ac3342c291bd27695f9fac987`
- First-parent tree: `ef2a73250462f8835b5d2a65f617753bb73ebd7c`
- Merge tree: `ef2a73250462f8835b5d2a65f617753bb73ebd7c`

The equal trees prove the merge added protected-main ancestry without replaying its older
flat-delivery content. The semantic delta was already adapted in D-237: current guard behavior is
executed by the regression, and every root-document decision citation must resolve.

## Acceptance boundary

The first-parent focused run passed 179 claims/pipeline tests with Ruff and formatting clean. The
canonical `scripts/verify.sh` run at the later documentation tip is the release-grade acceptance;
this file must not be read as a substitute for that execution.
