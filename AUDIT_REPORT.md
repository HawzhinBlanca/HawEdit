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
- The WSL2 setup installs pinned PyPI packages but package-manager integrity is not the same as
  vendored/checksummed model assets; Meta's model-card downloader still owns those remote bytes.
- **Hugging Face model revisions are pinned as of 2026-08-09** (D-073). `models/revisions.json`
  fixes **all six** downloadable repositories to commit SHAs that were read from the Hub and then
  verified against the weights on this machine, and `fetch-models.sh` refuses a repository with
  no pin rather than resolving a branch head. **Corrected 2026-08-09 (D-120):** this bullet said
  *five* repositories and called `pyannote/speaker-diarization-community-1` deliberately unpinned
  with "a test asserts it is the only one". D-075 pinned it — that repo is gated for *downloads*
  and public for *metadata*, so its revision was always a verifiable fact here — and
  `tests/test_models.py` now asserts `unpinned == []` with no exemptions. Measured: 6 pinned, 6
  registry entries with a download source, 0 unpinned.
- **`fetch-ffmpeg.sh` is pinned and checksummed as of 2026-08-09** (D-121). It was neither: the
  URL ended `/main/v8.0/linux.zip` — a branch path, so the bytes behind it could change — and the
  archive was unzipped, marked executable and run with no SHA-256 comparison. It is now fetched at
  commit `df95abcb0ce6efff710dda5ef28a2f6f1dc21493` and compared against
  `ca75b05e887c7a97676632f673031875847be83daa9794298fed9cef8cac14ad` **before** the unzip and the
  `chmod +x`, with `curl --fail` so an HTTP error page is not mistaken for an archive. Measured: the
  Git-LFS media endpoint serves a commit ref, and at this one it returned byte-identical content to
  what `main` returned that day — 142,008,975 bytes, both hashed in full. **The digest is ours, not
  upstream's:** the project still publishes none, so it attests which bytes this machine and CI have
  been running rather than which bytes the publisher intended. `README.md` and the CI step called
  this "pinned" while it was not; this bullet was the only accurate one of the three.
  `evidence/an-archive-fetched-from-a-branch-and-never-checked.md`. The fetch also retries a transient transfer error (D-123): a run failed with `curl: (92) … PROTOCOL_ERROR` 100 seconds into the same transfer that had completed in 2 seconds one run earlier, and retrying is safe only because the digest is compared before anything is unzipped.

## Honest release call

Call this a hardened, composed candidate pipeline. Do not call it production-ready until a real
Sorani ASR run, a real human editorial regression run and an authorized Vertex job have all
produced recorded evidence. Anything stronger would be marketing, not engineering.

## Verification evidence

- Clean isolated-worktree Windows/Python 3.12.10 gate, Ruff/formatting/mypy clean:
  **1,603 collected, 1,603 passed, 0 skipped** on 2026-08-09.
  That is a measurement at a date, not a running total — the suite ratchets, so this figure will
  fall behind `scripts/test-count.floor` and that is correct. It is dated because the number
  recorded here was 1,063 and read as current for as long as nobody checked it;
  `tests/test_claims.py` now requires the date rather than pinning the number.
- Clean Python 3.12 wheel install: `pip check` clean; `hawedit`, `hawedit-asr-bench`,
  `hawedit-editorial-bench` and `hawedit-asr-setup` all start from the installed wheel.
- Wheel contains the Kurdish font/OFL, model-source manifest, WSL worker and setup module.
- **The wheel build is reproducible as of 2026-08-09** (D-120). It was not: two consecutive
  `pip wheel --no-deps` runs at one unchanged tree produced the same **333,362 bytes** and the
  hashes `a7c3b2f1c280aff4…` and `38d1d2475c46e120…`, because nothing set `SOURCE_DATE_EPOCH` and
  every ZIP entry carried the mtime of the instant it was written. `scripts/build-wheel.sh` now
  takes the epoch from the commit's own author date and prints the digest, and two builds are
  byte-identical. **No SHA-256 is quoted here, and the reason has changed:** the digest is
  per-commit by construction, so an inlined hash would be stale at the next commit and would read
  as a claim about this code rather than about one build of it. Compute it with
  `bash scripts/build-wheel.sh`. A test asserts both halves — two builds identical, and every ZIP
  entry stamped with the commit rather than the clock. `evidence/two-builds-of-one-commit.md`.

That evidence proves build/install/integration behavior. It does not turn absent real Sorani and
human editorial benchmark results into numbers, and it does not prove a confidential Vertex
tenant's retention policy.
