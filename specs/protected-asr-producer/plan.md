# Protected ASR Producer Plan

Approved-by: Wareen, 2026-10-14, explicit "Approve the protected-ASR producer plan" reply.

This extends approved D-329 diagnostics to the separately admitted producer.
Human approval is recorded; current security/resource/model evidence remains required. Existing
RT2B controller work continues under its already approved launch plan.

1. Complete actual caller maps and GPU combined-policy regression first. Reuse
   non-GPU controller servicing fence; worker GPU Landlock remains mandatory;
   final controller GPU Landlock/fence/inspection before Snapshot return. Prove
   direct-leaf Landlock and stronger alias denial separately. Keep old default
   assertions exact; no broader writable proc/root/scratch or emulated calls.
2. Inventory/hash the complete existing Python3.12/Torch/SDK/driver/source/model/
   input closure and actual capacity before copying. No new interpreter/model,
   installation or dependency upgrade. Keep diagnostic defaults. Proposed
   production maxima:7200s inference plus separately bounded preparation/drain,
   at most100000 declared files/128GiB image/64threads. Measured closure must fit;
   evidence may lower configuration but cannot silently raise these ceilings.
   Use offline caches/no bytecode/cache writes and explicit small CPU-thread
   settings before imports. Fresh actual CUDA tensor precedes model release.
   The image ceiling is not an RSS/VRAM/effect limit: admission must verify actual
   owned resource guards and effect drain, or refuse. No capacity metadata alone
   authorizes model release.
3. Extract shared canonical inference from run_request only where required,
   preserving all adapters/origins/alignment/completion and existing CLI writes.
   Add bounded typed private-channel segment/result transport:64KiB frames,
   at most16MiB transcript result, monotonically bound identity/sequence/hash,
   host-owned atomic checkpoint persistence and acknowledgment. No worker
   writable scratch, checkpoint directory or caller-supplied executable.
4. Bind a protected producer to the existing shared pipeline builder and fixed
   DBOS ID-only workflow with current runtime/model/security authorization,
   original owner lifetime, resource guards, billing and restart reconciliation.
   Generate current-source receipts normally after actual verification; do not
   copy or forge an old receipt. Qualified current VEX review remains a model
   release prerequisite, not fulfilled by this plan or engineering approval.
5. Run current ZAR38 end-to-end under champion policy. Use saved credentials only
   through existing host transport, transcript-only Gemini2.5 route and total
   US$5 cap. Resolve Community-1 access without accepting unseen licence terms.
   Retain every refusal. Render meaningful complete-sentence private candidates
   with accurate aligned Sorani captions and evidenced framing; inspect real
   decoded video/audio, request native caption/meaning review, then immutable
   corrections and signed promotion through existing reconciliation.

One writer, one sequential implementation unit at a time, test-first and exact
`bash scripts/verify.sh` after each. Local-only reviewed commits; no ledger
promotion without green gate and same-SHA CI. No push/publication or10/10 claim
from this test. Owner packet includes current VEX review, gated-model rights if
needed, native-Sorani review and final trusted reviewer configuration.
