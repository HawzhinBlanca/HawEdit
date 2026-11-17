# Production ASR First-Failure Plan

Approved-by: Wareen - 2026-10-04, explicit "approved, go bck work" following the scoped
native/WSL hard-stop policy proposal. No spending, model, licence or publication approval.

Baseline: 3fa765cd2dd48900fc900c949f63df2648eb7430. Approved parent T2/T3 scope;
diagnostic retention versus production admission is recorded in D-278.

1. Add named first-failure and damaged-reuse tests, then run the complete new test module
   against unchanged production source and preserve failures.
2. Add a bounded production failure carrying original diagnostic inputs and explicit
   missing-speech/correction records. Add strict keyword-only helper behavior, leaving
   diagnostic accounting available. Map new helpers before production adoption.
3. Adopt strict behavior in native production and the WSL worker, with no production output
   written after failure. Refuse supplied/reused damaged raw before normalization,
   sentence/discovery/judge/render/delivery or Stage 1 success checkpoint. Preserve raw bytes,
   failure collections and a truthful skipped/refused transcript event.
4. Transparently update the one old WSL correction-success regression to the approved
   refusal contract, retaining its canonical-word/offset/provenance/no-gap/rejection
   assertions as explicit diagnostics and adding no-output assertions. Do not silently
   relabel a production success or weaken the preserved diagnostic evidence.
5. Run complete affected caller modules, then exact `bash scripts/verify.sh`. Review and
   commit locally under existing owner approval, never push. Keep source frozen during the
   committed full gate; preserve VEX failure and do not rebind a qualified review.

No ledger promotion without an actual green gate and applicable same-SHA CI. Existing
canonical ASR interfaces/raw schema/worker request identity remain. This unit does not
repair the repeated-digit draft, prove accuracy or make ZAR38 publishable. First-failure
diagnostic data carried by an exception is not a durable partial ASR checkpoint; no
cross-process completed-prefix recovery is claimed. Independent native references,
genuine current-source security review and finite cloud authorisation remain required.
