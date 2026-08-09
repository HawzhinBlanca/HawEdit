# HawEdit deep audit — 2026-08-08

## Verdict

The application is now composed end to end in code. It is still not production-proven.

The earlier architectural blockers are closed: the runner can produce canonical ASR, bounded
Qwen retrieval/reranking, survivor-only VideoChat3 readings, automatic sentence selection,
pixel-grounded Gemini judgments, TimeLens evidence, Vertex routing and dynamic face-aware
reframing. The gate proves those joins and their refusal paths. It does not prove model quality
on real Sorani client footage.

## Blockers closed

- Canonical OmniASR is a first-class runner/CLI producer. Stage 0 VAD regions are cut, sent to
  the official LLM decoder and CTC emissions, Viterbi-aligned, shifted to the media clock and
  persisted through the immutable transcript store. Windows automatically uses one WSL2 worker;
  Linux executes locally. The WSL request is path-confined and the output is create-once. A
  wheel-safe setup command provisions a source-fingerprinted user runtime rather than assuming
  the process is running from a checkout. The CTC forward now also produces its official greedy
  hypothesis; the production router invokes rzgar for the bottom confidence quartile or material
  disagreement, uses its correction for that segment, then CTC-realigns the final text. The full
  route has run through the real CLI on both RTX 3090 Ti GPUs.
- `VisualComposer` owns extraction → embedding → top-50 retrieval → rerank-all → keep 5–10 →
  VideoChat3. Only exact survivors reach Path B, and returned IDs/scores must match reranker
  provenance. Media with fewer scenes than the survivor count is refused outright, not
  shortened to whatever it has; episode length is not treated as one
  model-call VRAM budget. The old unranked `read_scenes=` injection is now refused, so library
  callers cannot bypass the survivor slice and promote an episode wholesale.
- Stage 4 extracts up to 20 real JPEG keyframes from the exact candidate slice. The identical
  multimodal parts go through token counting and generation; text-only visual judgment refuses.
  Each extraction owns a private namespace, so retry debris cannot become current evidence.
- Hosted-model numeric output is accepted only with its exact JSON type. Booleans, numeric
  strings, NaN/infinity and invalid token counts fail before ranking, fusion, billing or judging.
- Automatic selection chooses complete contiguous sentences wholly contained by the best
  per-path-ranked survivor. A partial overlap cannot borrow a candidate's scores or SV6D.
- TimeLens2 is wired into Stage 5 over overlapping scene windows. Window-relative spans are
  shifted to the media clock, and only evidence overlapping the anchored sentence can extend it.
- Rendering accepts time-varying focus points from dominant-face continuity tracking and labels
  the result `face_tracked`; it no longer claims every crop is static centre.
- Rendering requires recorded human review independently of automated QC and refuses encoded
  duration more than one measured frame above or below the reviewed clip.
- Canonical transcript raw/digest publication is serialized per media id across threads and
  processes. A competing writer cannot observe the reservation before the pair is complete;
  interrupted orphan evidence is refused rather than reconstructed.
- A delivered clip is now one write-once directory transaction. ASS, MP4, SRT, EDL and editing
  JSON remain private until the exact non-empty set has been flushed and atomically renamed;
  a sidecar failure publishes no render, and concurrent workers cannot mix or replace bundles.
- Confidential routing exists through Vertex REST with Application Default Credentials. It
  requires an attributed zero-data-retention confirmation and never places credentials in URLs.
- A strict editorial regression manifest now requires real source media, exact paired spans,
  two named reviewers, at least 20 items and at least five items per Sorani dialect.
- The clean-wheel dependency audit found FontTools 4.55.3 affected by CVE-2025-66034. The base
  wheel and isolated Stage 1 WSL runtime now share the smallest fixed exact pin, 4.60.2; a fresh
  Python 3.12 environment passes `pip check`, real Kurdish font coverage and a third-party
  `pip-audit==2.10.1` scan with no known vulnerabilities (D-088). This is dated evidence, not a
  claim that future advisories cannot appear.

## Remaining production blockers

These cannot be truthfully solved from the checkout alone:

1. **No real labelled Sorani corpus is present.** There is still no defensible CER, named-entity,
   code-switch, alignment or dialect-regression number for the canonical ASR on Hawa's material.
2. **No real editorial regression manifest is present.** Hook quality, cultural landing,
   misleading-edit rate and judge preference remain unmeasured. Unit tests are not human review.
3. **Cloud authorization is external.** Vertex code exists, but the project, billing, ADC,
   contractual ZDR configuration and named approver must be supplied by the operator.
4. **Reframing is face-aware, not active-speaker-aware.** Without gated diarization and a
   speaker-to-face association model, multiple visible faces can still make the wrong person the
   crop target. The current tracker prefers continuity and face area; it does not infer speech.

## Secondary debt

- Atomic delivery is a namespace-visibility guarantee on one filesystem, not a promise that a
  storage controller survives power loss. File contents are flushed before the directory
  rename; a process crash may leave a hidden staging directory, which does not block a retry and
  is intentionally not recursively deleted without inspection.
- The current automatic cross-path priority uses rank and path agreement because verbal and
  visual scores are not calibrated to the same scale. A learned fusion policy must wait for the
  real §8.2 set.
- The WSL2 setup installs exact OmniASR 0.2.0/fairseq2 0.6/Qwen packages with a matched
  Torch/torchaudio 2.8 pair. HawEdit now owns exact byte identities for the 43.5 GB canonical
  LLM-7B/CTC-3B/tokenizer set and official card document, atomically provisions only matching
  downloads, freezes external card sources, validates effective model/tokenizer policy and hashes
  every asset again before model construction. Both real models load through aliases to the held
  verified descriptors, and failed setup invalidates readiness
  (`evidence/omniasr-asset-integrity.md`).
- WSL readiness is a validated receipt over an exact source snapshot and one
  versioned/revalidated venv generation. Setup is cross-process serialized; launch re-hashes the
  copied worker and probes the recorded interpreter, package versions, assets and CUDA route.
  Importability alone cannot make OmniASR appear ready. This does not claim transitive venv-byte
  immutability (`evidence/wsl-runtime-receipt.md`).
- **All six Hugging Face repository revisions are pinned as of 2026-08-09** (D-073/D-075).
  `models/revisions.json` fixes every fetchable repository to a full commit obtained from Hub
  metadata, and `fetch-models.sh` refuses any repository with no pin. Four local visual
  checkpoints were cross-checked against their commits; pyannote's revision is public metadata,
  while its gated file downloads remain blocked by `BLOCKED.md` #4.
- Project-managed checkpoint provisioning is transactional and automation-visible: verified-status
  planning, a byte-only root override with separate trusted metadata, full-SHA runtime validation,
  private resumable staging, exact manifest verification, locked native no-replace publication,
  preserved invalid/concurrent finals and aggregate nonzero
  failure (`evidence/checkpoint-provisioning.md`). Consumers hold the matching shared lock from
  byte verification through config/recipe parsing and model construction, preventing a verified
  path from being reopened after cooperative replacement; the Windows host lease spans the WSL
  validator boundary (`evidence/checkpoint-load-binding.md`).
  The code/test boundary is closed; a fresh full-size real-model load under it is not yet measured.
- The project-fetched Linux ffmpeg archive is addressed by an immutable upstream commit and its
  Git-LFS SHA-256 is verified before unpacking.
- `hawedit-release` makes source-to-wheel bytes reproducible and emits checksummed Git
  provenance plus a deterministic SPDX 2.3 SBOM. The SBOM binds the exact wheel, bundled Noto
  font, and every base/optional `Requires-Dist` relationship without inventing unresolved
  dependency versions. Its two builds now run under a private, hash-locked Pip/Setuptools
  toolchain and provenance records that builder identity; an ambient backend cannot silently
  change the wheel. Publication also requires an explicit successful official `main` push gate
  for the exact release SHA and records its run/job in provenance; a clean but untested commit is
  no longer publishable. A permission-separated workflow now requires clean 3.11/3.12 installed-
  wheel smokes before defining GitHub-OIDC attestations for the exact four-file release set without
  exposing attestation authority to repository build code; its
  first post-merge protected-`main` run is still required before authenticity has live evidence.
  Versioned durable publication and transitive deployment hash locks remain open; OmniASR
  package-asset byte identity is closed separately at runtime.

## Honest release call

Call this a hardened, composed candidate pipeline. Do not call it production-ready until a real
Sorani ASR run, a real human editorial regression run and an authorized Vertex job have all
produced recorded evidence. Anything stronger would be marketing, not engineering.

## Verification evidence

- Full Windows gate, Ruff/formatting/mypy clean: **1,457 collected, 1,457 passed** on 2026-08-09.
  That is a measurement at a date, not a running total — the suite ratchets, so this figure will
  fall behind `scripts/test-count.floor` and that is correct. It is dated because the number
  recorded here was 1,063 and read as current for as long as nobody checked it;
  `tests/test_claims.py` now requires the date rather than pinning the number.
- Clean Python 3.11.15 and 3.12.13 current-wheel installs: `pip check` clean, installed font/model
  metadata present; `hawedit`, `hawedit-asr-bench`,
  `hawedit-editorial-bench`, `hawedit-asr-setup`, `hawedit-credentials` and `hawedit-release`
  all start from the installed wheel.
- Wheel contains the Kurdish font/OFL, model source/revision manifests, WSL worker/setup module and
  the source-fingerprinted OmniASR asset allowlist.
- Fresh FontTools 4.60.2 compatibility environment: `pip check` clean, real bundled Noto Kurdish
  coverage passed, and `pip-audit==2.10.1` found no known third-party vulnerabilities. Three
  independent dependency-pin mutations were caught and restored (`evidence/dependency-security.md`).
- Real Stage 1: the rzgar checkpoint reproduced its shipped Sorani demo reference exactly at
  4,250,408,448 peak allocated bytes on GPU 1; the real CLI then ran OmniASR LLM-7B + CTC-3B,
  validator routing and Viterbi timing over the committed media fixture in 212.9 seconds from a
  warm asset cache. A separate integrity run rehashed all 43.5 GB and loaded both actual model
  classes through held descriptors in 249 seconds. The fixture is synthetic Kurmanji, so this
  proves execution, not Sorani CER.
- Stage 0 now owns the video media clock: the real fixture's padded VAD previously ended at
  4180 ms against 4162 ms of footage; it is intersected at 4162 ms before canonical ASR, and a
  runner integration test proves no speech region handed downstream can exceed the media end.
- A real 30000/1001 transcode completes JSON/SRT/EDL delivery with SMPTE drop-frame timecode;
  25 fps remains non-drop and unsupported 24000/1001 refuses before any sidecar write.
- Real pipeline delivery publishes one exact ASS/MP4/SRT/EDL/JSON directory. Tests inject ASS
  and sidecar write failures and a two-worker publication race; failures expose no partial set.
- `hawedit-release` first verifies an explicit official `main` push run whose workflow, exact SHA,
  successful `gate` job and mandatory steps all match the clean Git `HEAD`, then derives
  `SOURCE_DATE_EPOCH` and exports that Git object twice with replacement refs disabled. Each wheel
  builds from its own pristine source tree under a private builder populated only from hash-locked
  Pip 26.2.1 and Setuptools 84.0.0 wheels. It refuses unequal bytes, validates release-critical
  package data, and atomically emits
  the wheel with `SHA256SUMS`, SPDX 2.3 JSON and stable revision/gate/builder provenance. The
  independent `spdx-tools 0.8.5` validator accepts the emitted document. Digests intentionally
  live beside the artifacts instead of in this changing source file. The OIDC workflow is
  permission-separated, installed-wheel gated on 3.11/3.12, exact-set tested and action-linted,
  but not yet live-proven from default
  `main`; transitive environment hash locking also remains open supply-chain work
  (`evidence/release-builder-lock.md`, `evidence/release-exact-gate.md`,
  `evidence/release-attestation.md`, `evidence/python-support.md`,
  `evidence/omniasr-asset-integrity.md`).
- Cross-Python release proof: Python 3.11.15 and 3.12.10 each emitted the same 329,973-byte wheel
  from revision `8d4810d28fd1`, SHA-256 `7765db5414dd69f8679f0646b41376907978b95e68d9a260d7ad64e49cde34b9`.
  Provenance differs deliberately because it records the measured interpreter.
- CI action runtime audit: exact-SHA run 31291508018 exposed deprecated Node-20 action runtimes.
  Checkout 7.0.1 and Setup Python 7.0.0 are now pinned to audited full commits whose official
  `action.yml` declares Node 24; a focused regression refuses rollback. Exact-SHA run 31291847181
  completed successfully with zero check-run annotations (`evidence/ci-actions.md`).

That evidence proves build/install/integration behavior. It does not turn absent real Sorani and
human editorial benchmark results into numbers, and it does not prove a confidential Vertex
tenant's retention policy.
