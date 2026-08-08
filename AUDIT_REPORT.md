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
  the process is running from a checkout.
- `VisualComposer` owns extraction → embedding → top-50 retrieval → rerank-all → keep 5–10 →
  VideoChat3. Only exact survivors reach Path B, and returned IDs/scores must match reranker
  provenance. Media with fewer scenes than the survivor count is refused outright, not
  shortened to whatever it has; episode length is not treated as one
  model-call VRAM budget. The old unranked `read_scenes=` injection is now refused, so library
  callers cannot bypass the survivor slice and promote an episode wholesale.
- Stage 4 extracts up to 20 real JPEG keyframes from the exact candidate slice. The identical
  multimodal parts go through token counting and generation; text-only visual judgment refuses.
- Automatic selection chooses complete contiguous sentences wholly contained by the best
  per-path-ranked survivor. A partial overlap cannot borrow a candidate's scores or SV6D.
- TimeLens2 is wired into Stage 5 over overlapping scene windows. Window-relative spans are
  shifted to the media clock, and only evidence overlapping the anchored sentence can extend it.
- Rendering accepts time-varying focus points from dominant-face continuity tracking and labels
  the result `face_tracked`; it no longer claims every crop is static centre.
- Confidential routing exists through Vertex REST with Application Default Credentials. It
  requires an attributed zero-data-retention confirmation and never places credentials in URLs.
- A strict editorial regression manifest now requires real source media, exact paired spans,
  two named reviewers, at least 20 items and at least five items per Sorani dialect.

## Remaining production blockers

These cannot be truthfully solved from the checkout alone:

1. **No real labelled Sorani corpus is present.** There is still no defensible CER, named-entity,
   code-switch, alignment or dialect-regression number for the canonical ASR on Hawa's material.
2. **No real editorial regression manifest is present.** Hook quality, cultural landing,
   misleading-edit rate and judge preference remain unmeasured. Unit tests are not human review.
3. **Cloud authorization is external.** Vertex code exists, but the project, billing, ADC,
   contractual ZDR configuration and named approver must be supplied by the operator.
4. **Canonical-ASR model execution is still unmeasured.** The WSL2 runtime path is real and both
   GPUs are visible, but this audit did not install/download the roughly 44 GB pair or claim an
   unrun full-model result. Visual models have separate real-fixture evidence in `evidence/`.
5. **Reframing is face-aware, not active-speaker-aware.** Without gated diarization and a
   speaker-to-face association model, multiple visible faces can still make the wrong person the
   crop target. The current tracker prefers continuity and face area; it does not infer speech.

## Secondary debt

- Render publication is now atomic and write-once: ffmpeg stages privately, the MP4 is measured
  before publication, partial encodes are removed, and a competing worker cannot overwrite the
  winner. The complete MP4/ASS/SRT/JSON/EDL bundle is still not one transaction, so a failure
  after render can require a fresh work directory rather than resuming the bundle in place.
- The current automatic cross-path priority uses rank and path agreement because verbal and
  visual scores are not calibrated to the same scale. A learned fusion policy must wait for the
  real §8.2 set.
- The WSL2 setup installs pinned PyPI packages but package-manager integrity is not the same as
  vendored/checksummed model assets; Meta's model-card downloader still owns those remote bytes.
- **Hugging Face model revisions are pinned as of 2026-08-09** (D-073). `models/revisions.json`
  fixes all five downloaded repositories to commit SHAs that were read from the Hub and then
  verified against the weights on this machine, and `fetch-models.sh` refuses a repository with
  no pin rather than resolving a branch head. `pyannote/speaker-diarization-community-1` is
  deliberately unpinned — gated, never downloaded here (`BLOCKED.md` #4) — and a test asserts it
  is the only one.
- The project-fetched Linux ffmpeg archive is addressed by an immutable upstream commit and its
  Git-LFS SHA-256 is verified before unpacking.
- `hawedit-release` makes source-to-wheel bytes reproducible and emits a checksum plus Git
  provenance, and CI's remote GitHub Actions are pinned to full commits. Releases are still
  unsigned, carry no SBOM, and package-managed OmniASR assets lack a project-owned byte manifest.

## Honest release call

Call this a hardened, composed candidate pipeline. Do not call it production-ready until a real
Sorani ASR run, a real human editorial regression run and an authorized Vertex job have all
produced recorded evidence. Anything stronger would be marketing, not engineering.

## Verification evidence

- Full Windows gate, Ruff/formatting/mypy clean: **1,072 collected, 1,072 passed** on 2026-08-08.
  That is a measurement at a date, not a running total — the suite ratchets, so this figure will
  fall behind `scripts/test-count.floor` and that is correct. It is dated because the number
  recorded here was 1,063 and read as current for as long as nobody checked it;
  `tests/test_claims.py` now requires the date rather than pinning the number.
- Clean Python 3.12 wheel install: `pip check` clean; `hawedit`, `hawedit-asr-bench`,
  `hawedit-editorial-bench`, `hawedit-asr-setup` and `hawedit-release` all start from the
  installed wheel.
- Wheel contains the Kurdish font/OFL, model-source manifest, WSL worker and setup module.
- `hawedit-release` derives `SOURCE_DATE_EPOCH` from clean Git `HEAD`, builds independently
  twice, refuses unequal bytes, validates release-critical package data, and atomically emits
  the wheel with `SHA256SUMS` and stable revision provenance. The digest intentionally lives
  beside the artifact instead of in this changing source file. Signing, SBOM generation and
  pinned model revisions remain open supply-chain work.

That evidence proves build/install/integration behavior. It does not turn absent real Sorani and
human editorial benchmark results into numbers, and it does not prove a confidential Vertex
tenant's retention policy.
