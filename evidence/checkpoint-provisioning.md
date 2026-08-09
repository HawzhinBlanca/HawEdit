# Transactional Hugging Face checkpoint provisioning — 2026-08-09

## Reproduced failures

The old checkout-only fetcher downloaded directly into each final checkpoint directory. `missing_weights()`
treated any existing directory—including an empty or interrupted one—as installed, so a failed
first download was skipped forever on every retry. The script then printed a readiness report whose
CLI always exited zero, masking total or partial failure from automation. Its advertised
`HAWEDIT_MODELS` destination also differed from the runtime's `HAWEDIT_MODELS_DIR`, and
`revision_for()` accepted any truthy string, allowing a custom `main` or tag to restore mutable
downloads. A later custom-root implementation still preferred `sources.json`, `revisions.json`
and `integrity.json` beside the mutable weights, so a checkpoint volume could redefine the very
identity used to approve it. POSIX `os.rename` could also replace a concurrently appearing empty
final directory despite the stated no-overwrite rule.

## Current transaction

- The wheel ships `hawedit-fetch-models`; the source-checkout shell script is only a launcher for
  that module. The optional `models` extra pins `huggingface-hub==0.36.2`, and the command refuses
  a missing or different client instead of mutating its own environment with `pip install`.
- Planning comes from exact `ModelStatus.available`, not path existence. An invalid existing final
  directory remains in the plan.
- `HAWEDIT_MODELS_DIR` is the single command/runtime override.
- That override selects mutable checkpoint storage only. Source, revision and byte identities are
  read exclusively from the checkout/installed metadata root; hostile lookalike manifests beside
  the weights are ignored.
- Every repository revision is runtime-validated as one lowercase 40-hex commit.
- The pinned Hugging Face client resumes into a revision-specific private sibling directory.
- Before any downloader call, an existing resume tree is recursively checked for owner, private
  mode or protected Windows DACL, regular/single-link members and absence of reparse/symlink
  objects. Fresh staging is created unpredictably, then atomically named as the deterministic
  revision resume before transfer. POSIX requires 0700; Windows atomically applies and validates a
  protected current-user/SYSTEM/Administrators DACL on the root and every inherited member.
- A writer lock serializes HawEdit publication. The complete staged file set is checked against
  `models/integrity.json`; roots/members that are links, reparse points, hardlinks or non-regular
  objects are refused, and fd/path identity is checked around hashing.
- Only a fully verified stage is published with a native no-replace primitive (`renameat2` on
  Linux, `renamex_np` on macOS, Windows rename refusal). A final that appears concurrently—even an
  empty directory—is preserved. A pre-existing invalid final is refused with an explicit
  quarantine instruction; HawEdit never deletes or overwrites it implicitly.
- Per-model failures are accumulated while remaining targets are attempted. The final full status
  still prints, but the command exits nonzero if any requested target failed, was gated without a
  token, lacked a source or could not verify/publish.

`verified_checkpoint_access()` uses the sibling shared lock for consumers, so cooperative HawEdit
writers cannot replace the directory while a model is opening it.

## Verification and limits

The combined focused run covered the installed fetch module, its shell wrapper, models, ASR and
Qwen consumers; Ruff,
formatting, targeted Mypy, Bash syntax and diff checks passed. Tests exercise invalid existing
finals, exact revision parsing, strict repository metadata, manifest preflight,
hardlink/reparse/file-set mutation, hostile mutable-root manifests,
verified-status planning, writer/shared-lock behavior, nonzero aggregate failure and an empty-final
no-replace race. A planted resume hardlink is refused before the fake Hub client can touch its
external victim; an over-permissive POSIX resume root and a real Windows `Everyone:F` DACL are
also refused. A subprocess hard-exit regression leaves one deterministic resume tree and the next
run consumes it. A real WSL probe independently reproduced Linux's no-replace refusal.

No live multi-gigabyte Hub download was performed in this change. A genuine locked Hub client did
download and validate a 21-file, 12,513,720-byte exact-revision test snapshot. The deterministic
active resume name supports crash recovery; its privacy comes from 0700/protected-DACL isolation,
not obscurity. Exact manifests prevent byte substitution, while the lock coordinates HawEdit
processes rather than privileged or same-account out-of-band filesystem writers.
An invalid final or preserved stage requires explicit operator cleanup. Those are stated operating
constraints, not hidden success claims.
