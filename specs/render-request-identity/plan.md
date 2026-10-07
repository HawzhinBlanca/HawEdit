# Retained Render Request Plan

Approved-by: Wareen, approved evidence-based-studio implementation and renewed
"continue the fix full fix" on 2026-10-07; scoped to the already requested
changed-render invalidation and immutable revision behavior.

1. Finish actual Serena symbol/caller map; document EARS and D-291.
2. Add failing regressions against the actual pipeline and real fixture media:
   changed render controls, missing/changed request binding, unchanged reuse,
   and a fresh headline revision with different decoded pixels.
3. Add deterministic bounded structured request hashing and strict optional
   Provenance binding. Do not add unsigned packet members or change ASR.
4. Adopt it in the retained single-candidate render path and recheck assets/code
   before consumption/publication. Preserve/refuse changed historical media;
   choose a new work directory for a revision rather than overwrite it.
5. Run all affected modules, lint/type/format, review local changes, local commit,
   then exact `bash scripts/verify.sh` on frozen source. No push. No ledger flip
   unless the exact gate and required same-SHA CI both pass.

This unit does not enable the unconfigured protected HTTP worker, claim complete
render runtime attestation, or implement the full studio revision UI.
