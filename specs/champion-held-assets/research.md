# Research

Baseline: `36c2d0130457856ef44e600eaa2a84b9d3b277cc`, clean primary checkout.
Scope: BLUEPRINT section 3 Stage 1 and section 7; D-181, D-260; BLOCKED #24.
Read owner Champion Supremacy and Verify at the Serving Path canon before editing.

Actual Serena LSP definitions and referencing-symbol results were captured before edits:
`C:/Users/Wareen/AppData/Local/HawEditEvidence/adapted-load-map-36c-20261006/serena-map.json`.
Rechecked source hashes on 2026-10-07: asr.py
`d53f977b5f8353314e9146d7566059418c33d7b7455c41e4f779b354f1d91608`, omni_assets.py
`8dd97bfffc0b5840217700c88a7d41f93d887aaff6f036b983def377c5fac9f7`.
Serena's file-symbol fallback warnings are retained in that capture; dynamic callers
are additionally grounded by repository search, not asserted absent from LSP results.

The stock loader uses held-descriptor aliases for all three canonical assets. The
default adapted loader instead imports first, loads the base checkpoint through a
URL-keyed cache, resolves the bundle tokenizer pathname, and lets PEFT reopen the
original directory. Fingerprinting before/after does not bind what those consumers read.

Read pinned installed runtime source, not an assumed API: fairseq2 0.6
`assets/download_manager.py` preserves file-URI alias paths; PEFT 0.19.1
`utils/save_and_load.py::load_peft_weights` opens local adapter safetensors before
considering pickle or Hub. Therefore a private directory containing only the three
held aliases can serve those consumers without changing their model recipe. Real
WSL consumers and real model construction still require verification.

Keep the schema-2 three-file fingerprint, champion bundle, derived vocabulary,
trainer's 7b architecture, Fairseq2 Linear registration, CTC 3b_v2/tokenizer, decoder,
completion policy, validator routing and stop behavior unchanged. No new dependency.
Descriptor binding protects pathname replacement; it does not authorize untrusted
weights or defend against privileged/same-UID in-place writers. Qualified current
VEX review, model/input provenance and release checks remain separate obligations.

Supplemental actual Serena map before the next correction:
`C:/Users/Wareen/AppData/Local/HawEditEvidence/champion-card-map-2e44930-20261007/serena-map.json`
at `2e449302b8144eb5d5c615ea34cf76fbe62f038d`, unchanged source. The private adapted
assembler now also has the new composition test as a caller. Read pinned fairseq2
`assets/store.py`: name lookup searches existing providers and applies environment
metadata. Freezing directories does not remove already-loaded provider metadata.
`models/hub.py::GlobalModelLoader.load` and tokenizer hub accept AssetCard objects,
bypassing name resolution. Use those same direct-card APIs already used by stock;
do not mutate the global metadata provider list or trust a derived name lookup.
