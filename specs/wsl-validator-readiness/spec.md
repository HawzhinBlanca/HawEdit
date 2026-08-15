# Specification — WSL validator readiness

## Acceptance criteria

- **AC-1:** WHEN the exact rzgar checkpoint is present on Windows and the canonical WSL runtime
  probe succeeds, THE readiness report SHALL mark the validator available and retain the exact
  checkpoint path and byte count.
- **AC-2:** WHEN the rzgar checkpoint is exact but the Windows WSL runtime is invalid, THE readiness
  report SHALL mark the validator unavailable with the runtime refusal while the fetch planner
  SHALL NOT schedule its bytes again.
- **AC-3:** WHEN the rzgar checkpoint is missing or fails its manifest, THE readiness report SHALL
  mark it unavailable and the fetch planner SHALL include it.
- **AC-4:** WHEN a non-validator checkpoint has exact bytes but its declared host loader is absent,
  THE readiness report SHALL remain unavailable while the fetch planner SHALL NOT redownload it.
- **AC-5:** WHEN the validator is evaluated on a non-Windows host, THE system SHALL retain the local
  `qwen_asr` importability requirement.
- **AC-5a:** WHEN an explicitly local adapter calls `assert_available` on Windows, THE system SHALL
  retain calling-interpreter `qwen_asr` readiness rather than inheriting the canonical WSL report.
- **AC-6:** WHEN the canonical Windows WSL producer resolves its validator, THE producer SHALL
  accept its path only through `verified_checkpoint_access` and SHALL hold that single exact-byte
  lease across request publication, WSL execution, and response parsing.
- **AC-7:** WHEN a report evaluates both OmniASR entries and the validator, THE canonical WSL runtime
  proof SHALL execute no more than once for that `ModelStore` instance.
- **AC-8:** WHEN runtime or byte verification fails, THE diagnostic SHALL remain bounded to the
  correct execution context and failure class and SHALL NOT claim that running the model fetcher
  repairs a runtime-only failure.

## Non-goals

- This change does not weaken checkpoint hashes, trust a mutable model-root manifest, or infer
  readiness from directory existence.
- This change does not install packages, fetch checkpoints, provision WSL, load model tensors, or
  alter validator output semantics.
- This change does not add a redundant pre-lease checkpoint hash before the producer's existing
  exact verification.
- This change does not claim Sorani accuracy; labelled CER/WER remains M0.13.
