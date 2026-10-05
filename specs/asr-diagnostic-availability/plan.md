# Implementation Plan

Approved-by: Wareen - 2026-10-05, "approve all and fix them".

1. Add failing unknown/partial/record-authority regressions.
2. Retain the checked raw transcript as optional diagnostic evidence on PipelineRun.
   Serialize recorded values from that record; otherwise retain partial details
   without asserting complete measurements. Document nullable contract in D-282.
3. Run affected regressions, review a local-only commit, then run exact
   bash scripts/verify.sh. Do not mark acceptance without green same-SHA CI.
4. Exercise the current CLI report on the actual ZAR source without an ASR
   producer, verifying null availability. This is a reporting test, not a new
   ASR-quality retest. Preserve the completed full-source failure evidence.

No spending, signing, model swap, fallback, transcript mutation or publication.
