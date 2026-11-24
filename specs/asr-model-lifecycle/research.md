# Research

Baseline: 379c7c8e97a41a0f3e4c322edf26c1cfa71bf432, package c1397cc2.
Read vault Champion Supremacy, Verify at the Serving Path and the 2026-10-07
held-input repair decision. BLUEPRINT sections 3 Stage 1, 4.2, 6, 7, 8.1;
D-181, D-260, D-278, D-281, D-284, D-285. Licensing decisions remain closed.

Actual Serena definitions/references before source edits:
C:/Users/Wareen/AppData/Local/HawEditEvidence/asr-lifecycle-map-379c7c8-20261007/serena-map.json.
Seven symbol pairs; source hashes unchanged. LSP fallback warnings and dynamic
Protocol limitations remain recorded; empty references do not prove absence.

align_segment calls _load, constructing both LLM and CTC although correction
alignment uses only CTC. Native and worker production draft all regions before
validation, but retain the unused draft model throughout Qwen validation.
Recovery can reuse every draft and still construct the unused LLM on its first
missing correction alignment. This is a real dependency/lifecycle defect, not
proof of a particular OOM or inference speedup.

Pinned torch 2.8.0 installed source was inspected through the supported WSL
interpreter: empty_cache releases unused allocator memory only, not live tensors.
memory_allocated measures this process's tensor bytes, not whole GPU occupancy.
Official corroboration: https://docs.pytorch.org/docs/main/generated/torch.cuda.memory.empty_cache.html
Use process-local allocated/reserved bytes and retained tensor/clock checks;
do not infer exclusive peak VRAM from nvidia-smi while owner training is active.

Preserve every canonical draft, CTC model/tokenizer, routing, numerical settings,
completion, first-failure halt and journal binding. Keep held verification before
imports; admit caches only after guarded context exit. No new dependency or model.
Full 379c7c8 gate: 4941 pass / 2 fail / 0 errors or skips, 4943 total.
Evidence-header omission is corrected separately without weakening its test;
qualified VEX source mismatch (#24) is not rewritten to obtain a pass.
