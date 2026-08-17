# Research — WSL validator readiness

## Question

How should §7 report and plan the rzgar Sorani validator when Windows intentionally loads it in
the receipt-verified WSL Stage 1 runtime rather than in the host Python process?

## Reproduced current-state defect

Measured 2026-08-15 on hawapc01 at accepted source
`bd055e19dc15f9dc4380d149ed3a4184ea77873d`:

- the exact rzgar checkpoint passed its 21-file manifest at 10,095,911,962 bytes;
- the source-bound Ubuntu generation `Ubuntu-a3a875601325fe6bd6497791` passed the live VEX gate
  with CPython 3.12.0, the exact 140-distribution identity including `qwen-asr==0.0.6`, three
  Omni assets totalling 43,546,500,168 bytes, and two RTX 3090 Ti devices;
- that route then completed the rights-cleared 2,313.8-second Stage 1 run and recorded rzgar as
  validator provenance;
- `python -m hawedit.models` nevertheless reported the validator unavailable because
  `ModelStore._status_for` tests `qwen_asr` importability in the Windows host interpreter;
- `ModelStore.missing_weights` derives download work from that complete runtime status, so an
  exact checkpoint with a missing or differently located loader is classified as missing bytes.

The WSL producer already contains an explicit bypass: it resolves the registered checkpoint path
without calling `assert_available`, then holds `verified_checkpoint_access` for the complete WSL
subprocess. The production path is therefore runnable while the operator report and fetch planner
say otherwise.

## Caller map

Serena is required by `AGENTS.md` but is unavailable in this Codex tool session. Exact `rg`
reference searches and direct symbol inspection were used instead.

| Symbol | Callers/consumers | Impact |
|---|---|---|
| `ModelStore._status_for` | `status`, `assert_available`, `missing_weights` | Currently conflates checkpoint bytes and execution runtime. |
| `ModelStore._omni_runtime_status` | both Omni registry entries | Existing cached proof of the canonical Windows WSL route. |
| `ModelStore.missing_weights` | `model_fetch.build_fetch_plan` | Must answer only whether immutable checkpoint bytes need fetching. |
| `ModelStore.assert_available` | local model adapters | Must retain complete runnable-component semantics. |
| `WslOmniAsrProducer.transcribe` | canonical Windows Stage 1 | Needs an explicit exact-byte assertion before its held cross-runtime lease. |
| `readiness_report` / `_print_status` | human and automation output | Must describe the actual canonical execution route. |

## Chosen bounded design

1. Factor one exact checkpoint-byte status path. It verifies presence, the pinned repository and
   revision, every manifest member, and the checkpoint size without consulting a loader.
2. `missing_weights` and a byte-only assertion use that path. An exact checkpoint is never
   downloaded again merely because its runtime is unavailable.
3. Complete canonical component status layers runtime readiness over verified bytes. The rzgar
   validator on Windows uses the cached canonical WSL runtime proof; on non-Windows it continues to
   require the local `qwen_asr` loader. `assert_available`, which local adapters call, deliberately
   retains calling-interpreter semantics. Other checkpoints retain their host-loader contract.
4. The WSL producer keeps its existing single exact verification inside
   `verified_checkpoint_access`, holding the host shared lease across the full WSL worker. Adding a
   second eager byte assertion would re-hash 10.1 GB immediately before that mandatory verification
   and is deliberately rejected.
5. Missing, corrupt, unpinned, or mismatched validator bytes remain unavailable and fetchable.
   An invalid WSL receipt makes the component unavailable but never makes exact bytes fetchable.
6. The existing WSL runtime probe remains cached once per `ModelStore`; no second 43.5 GB asset
   verification is introduced within one report.

This implements the D-064/D-131 runtime split without changing `BLUEPRINT.md`, model identities,
checkpoint trust manifests, or the validator's D-197/D-223 evidence-only editorial semantics.
