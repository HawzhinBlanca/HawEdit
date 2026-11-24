# Adapter Identity Research

2026-10-03. Clean baseline 2cedcca65d0981544f09ab9bcb6cd1fb3e73e86e, producer
8dc4fe8550ec6e54a1abf02b51faee8284fdc11d4992f6f6ed4110fa97b66a1b. Read project vault
canon/checkpoint and current source first. Previous goal turn made progress: signed execution
authority committed, exact gate 4421 passes/one VEX binding failure, no skips; not acceptance.

Actual cached Serena 1.7.1.dev0 LSP map has twelve successful definition/reference queries
(adapter-identity-before-map.json); raw log is in LocalAppData/HawEditEvidence. The worker
and native/WSL producers are real interfaces, not invented signatures. Several calls use
protocol/getattr dispatch and do not appear as method references; inspect those call sites.
Two supplemental class/constructor queries in adapter-identity-constructor-map.json preceded
the constructor edit, for fourteen queries overall. The constructor has no direct LSP
references; the class map includes nineteen. Dynamic dispatch is not assumed to be absent.

## Reproduced Source Defects

adapter_fingerprint hashes only concatenated config/weights, truncated to sixteen hex digits.
_load_adapted_llm selects exactly one bundle *.model tokenizer and derives vocabulary from
it. Thus tokenizer changes leave the reuse identity unchanged. Concatenation also omits file
boundaries and roles. Whole-file read_bytes needlessly retains the weights in memory.

WslOmniAsrProducer sends model_identity, but asr_worker.run_request ignores it. The host
checks only returned media_id, not returned adapter identity. Native producer/worker read
adapter_name after inference; a mutable bundle can relabel results, and the backend's cached
pipelines are not bound to the identity observed at load. These are provenance/cache defects,
not a new ASR quality or exploitation measurement.

## Approved Repair Scope

Necessary T3 protected-worker model-identity prerequisite under the already approved parent
plan and D-276, BLUEPRINT sections 2/3/7; D-181/D-260 preserve the actual champion/tokenizer
recipe. No model, vocabulary, alignment, architecture, licence, or runtime dependency change.
Use versioned role/name/size/hash identity of config, safetensors and the unique tokenizer.
Stream bounded chunks through stable non-linked regular files and recheck the whole input set.
Missing/ambiguous tokenizer refuses before inference. Use the full SHA256, invalidating old
sixteen-digit identity rather than rewriting old transcript artifacts or accepting stale reuse.
Conflicting persisted requests explain source/segments/validator/adapter changes, preserve
prior bytes and require a new work directory after recovery reconciliation, not deletion.

Capture expected identity before inference, compare after all validator/alignment work, and
file output under that unchanged identity only. Adapted bridge requests require matching
current identity; stock bridge bytes remain unchanged. Host refuses a foreign returned adapter
or changed local bundle. A cached backend refuses changed/removed/switched bundle rather than
returning old loaded models under new identity. Preserve explicit stock selection and original
ASR/artifact records; no silent re-transcription, overwrite, or stock fallback.

Identity observation is not licence authentication or verify-to-load security. The adapted
loader's held-descriptor/base/PEFT gap (#24), champion rights (#21), actual producer runtime,
owner HTTP sessions and protected worker adoption remain mandatory. Per-segment hashing has
unmeasured overhead; no throughput or real-inference claim without the recorded licensed run.

Test the real filesystem/worker/host contracts and all mapped caller families first, then
run exact bash scripts/verify.sh on frozen clean committed source. No task acceptance until
canonical gate and same-SHA required CI pass. No new paid/cloud/model inference is authorized.
