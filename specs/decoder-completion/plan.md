# Decoder Completion Repair

Approved-by: Wareen - 2026-10-05, "approve all and fix them".
Ordinary safety repair only; no spending, licence acceptance, new trust enrollment,
model/beam/segmentation change, security clearance or release approval.

One implementation unit, one writer, test first:

1. Add regressions for sampled-token completion and cache/pipeline/worker paths.
2. Integrate the real-model-tested observer; validate pinned upstream code/classes,
   observe every existing segment invocation, serialize validation and observation,
   reject changed bindings/configuration, restore on all paths. Preserve algorithm.
3. Route actual canonical transcription through it while keeping independent CTC
   forward parallel. No alignment after refusal.
4. Add separate admission-policy cache identity. Refuse old/malformed/mismatched
   immutable records before expensive inference. Preserve positional compatibility
   and canonical bytes; no policy claim for injected fake native backends.
5. Run complete affected test files, lint/type/format, review local diff and commit
   locally only. Run exact bash scripts/verify.sh; no bypass of known VEX failure.
6. Refresh runtime through supported source-bound setup, test integrated real
   backend and run fresh immutable full ZAR38 production-ASR diagnostics. Preserve
   every failure; no paid call, publication, native accuracy or 10/10 claim.
7. Record evidence and append vault milestone. Ledger changes require prescribed
   script after green gate and applicable same-SHA CI; neither is assumed.
