# Isolated Runtime Security Migration Research

Baseline: dddd065bd396059c1c4c49cdbef75f488ed7e70a, 2026-10-07.
Read owner canon (Champion Supremacy, Verbatim Law, Propose/Commit Split),
current-source readiness and runtime migration research in the central vault.

Actual Serena SDK/LSP definition/reference pairs, source unchanged:
`C:/Users/Wareen/AppData/Local/HawEditEvidence/runtime-migration-map-20261007/serena-map.json`.
Mapped RUNTIME_REQUIREMENTS, RUNTIME_LOCK_SHA256, LOCKED_DISTRIBUTIONS,
_environment_digest, _generation_name, provision_wsl_runtime,
load_wsl_runtime_receipt and probe_wsl_runtime. No signatures invented.
Additional actual HOST_LOCK_SHA256 mapping and downloaded wheel metadata:
`C:/Users/Wareen/AppData/Local/HawEditEvidence/host-security-research-20261007/research.json`.

Current official receipt verifies canonical assets, complete locked package
inventory and import/CUDA readiness, not neural equivalence or security approval.
Live VEX gate refused expired review, source drift and seven findings. The raw
refusal is preserved in the vault's current runtime migration research. Blocker
#24 remains open; do not change its policy source/date/hash/dispositions to pass.

Primary maintainer advisories identify urllib3 2.8.0 as the fix for proxy TLS
separation, streamed Deflate no-progress and unbounded chunk-size lines:
https://github.com/urllib3/urllib3/security/advisories/GHSA-8988-9cw3-xx77
https://github.com/urllib3/urllib3/security/advisories/GHSA-gh4c-6fx4-qh6g
https://github.com/urllib3/urllib3/security/advisories/GHSA-vxq7-64xx-v4gw
Werkzeug 3.1.9 fixes Windows special-device paths:
https://github.com/pallets/werkzeug/security/advisories/GHSA-g6x2-hccm-hh4m
Rechecked primary sources and PyPI release JSON 2026-10-07. Verify downloaded
wheel bytes against published hashes before installing or claiming a repair.

Qwen ASR 0.0.6 transitively pins Transformers 4.57.6 / Accelerate 1.12.0.
The native GPU extra separately pins Accelerate 1.14.0. Neither issue closure
nor merged upstream code proves installed fixes. Major-version migration needs
actual champion/CTC/validator/PEFT compatibility and development-media evidence.
Do not remove the validator or substitute stock ASR to solve dependency conflict.

The existing environment digest includes complete packages and both lock hashes;
changing only the two HTTP utility pins generates a different venv directory.
Official provisioning can use an explicit isolated runtime root; no new runtime
selection mechanism is needed. Preserve the old generation and receipt bytes.
Host model/GPU locks also contain urllib3 2.7.0. Their maintainer generator has an
August cutoff; a truthful targeted regeneration is a separate unit, not a silent
hand-edit or full unconstrained dependency resolve.

Scope: BLUEPRINT sections 2, 3, 6, 7 and 8.1; D-064, D-261, D-285 and D-293.
No corpus license, gated diarizer, paid cloud, reviewer trust or publication
permission is inferred. Owner/editor/reliability/CI obligations remain.

## T2 Checkpoint Boundary, 2026-10-07

Actual source-unchanged Serena definitions/references on clean140d06d:
`C:/Users/Wareen/AppData/Local/HawEditEvidence/model-security-consumers-map-20261007/serena-map.json`.
Mapped QwenSoraniValidator._load, assert_transformers_config_safe,
verified_checkpoint_access, _WEIGHTS_RUNTIMES and worker_journal. The existing
config guard runs inside verified checkpoint access before Qwen/visual imports.
Integrity verification rejects changed/unmanifested bytes, links and nonregular
members, but config validation does not check shard index target semantics.

A real one-weight CPU model on the isolated candidate's Accelerate1.12.0 loaded
owned temporary payloads outside its checkpoint via relative/absolute index
paths after the existing config guard accepted them. Contained control passed.
This does not claim untrusted models passed the full manifest-integrity boundary.
Raw probe: Codex MSIX canonical HawEditEvidence/checkpoint-boundary-probe-20261007.
Original launch failed missing snapshot PYTHONPATH; corrected launch succeeded;
both recorded, no model assets modified. Current installed TimeLens/VideoChat
indexes are64836/75369bytes and use sibling regular safetensors shards.

Actual Accelerate1.15.0 source still joins index values unchecked:
https://raw.githubusercontent.com/huggingface/accelerate/v1.15.0/src/accelerate/utils/modeling.py
Complete path/nonregular fix proposal closed without merging:
https://github.com/huggingface/accelerate/pull/4214
Thus a new version number is not a demonstrated repair. Prefer a narrowly scoped
pre-load index guard without breaking Qwen's exact dependency constraints. This
mitigates owned loading boundaries only, not the installed library universally.
Qualified review and possible later compatible upstream migration remain open.

Full raw live scanner retained by an observer forwarding the real scanner return
unchanged, no mocked evaluation; actual admission still refuses.141 dependencies,
21 raw vulnerability entries/15 alias-deduplicated findings;3 new undispositioned.
All15 need current review because the old policy expired and source/lock drifted.
Raw canonical HawEditEvidence/refused-audit-full-report-v2-20261007/audit.json SHA
445307f6029974363e2a98e17093a20b5e969fe6ad17030e0149fe32ab50bf7f.

T1 exact gate:5130pass/1historical VEX binding failure/0errors/skips on clean140d06d,
source unchanged. No row accepted. Real560 adapter tensors and development text/
CTC/word comparisons pass, not CER or reel quality. The genuine validator phase
diagnostic is retained in HawEditEvidence/validator-phase-timing-20261007; slow
verification/loading/inference are separate, concurrent-gate diagnostic evidence,
not controlled acceptance throughput. Do not remove integrity checking for speed.
