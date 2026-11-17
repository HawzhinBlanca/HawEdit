# Production ASR First-Failure Research

Date: 2026-10-04 UTC. Baseline: clean local
3fa765cd2dd48900fc900c949f63df2648eb7430. Source facts, not acceptance measurements.

The owner's FINAL 2026-08-11 Champion Supremacy canon requires immediate stop on the
first draft, refinement, alignment or decode failure. Earlier D-135 accounts for failed
regions and D-223 preserves an aligned canonical segment when a proposed correction
fails. These diagnostic distinctions remain valuable; production continuation conflicts
with the later canon. Wareen explicitly approved the scoped conflict resolution on
2026-10-04: "approved, go bck work" after the presented hard-stop proposal.

`transcribe_prepared_segments` catches regional exceptions and continues. Native
`OmniAsrProducer.transcribe` and WSL `asr_worker.run_request` both use it, then use
`_validate_hard_segments`, which also continues after correction failures. WSL output is
written exclusively only after assembly. `run_pipeline` stores/verifies supplied or
reused raw, copies failure collections into its report, then normalizes, checkpoints
Stage 1, segments and indexes without refusing those collections.

Actual successful pre-edit Serena map is recorded in asr-stop-before-map.json. The earlier
eleven-query ASR admission v3 map covers native/WSL producers, raw/failure records, worker,
assembler and pipeline reports. Its four source hashes were rechecked identical at this
baseline. Original failed map attempts and LSP containing-symbol warnings are retained;
they are not presented as successful caller evidence. New helpers must be mapped before
adoption into existing callers.

The real ZAR38 development run retained three unaligned regions and two rejected
corrections. A separate current-source diagnostic reproduced the impossible repeated-digit
alignment. Those immutable historical artifacts are not rewritten by this repair.
Private original command/runtime/hash records remain outside this source snapshot.
No native-reference CER, speech quality, real billing, accepted performance or release
result is supplied by source inspection or unit doubles.

Scope: production first-failure dispatch and supplied/reused transcript admission.
No weights, tokenizer, decoder, scheduling, thresholds, external trust root, licence,
spending cap, review signature or delivery change. BLUEPRINT sections 3, 4.2, 5 and 8.1;
D-135/D-223; pro-kurdish-reel strict fail-stop; BLOCKED #24/#25 remain separate.
