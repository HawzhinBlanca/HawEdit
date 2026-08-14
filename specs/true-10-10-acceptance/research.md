# Research — true-10-10-acceptance

Date: 2026-08-15

Branch at research start: `claude/hawedit-project-setup-cciout`

Revision at research start: `193a6c4809c1758a1be02b7e1d1d7b43ce9d205c`

## Method

The configured session does not expose Serena, so the required symbol and caller mapping was
performed with read-only `rg`, `git`, and GitHub CLI queries. No production file was edited before
this research, specification, impact map, and plan were written.

The current pull request is #2, targets `main`, is mergeable, and has a clean merge state. Its head
is the revision above. The exact revision passed the canonical local gate with 2,442 collected,
2,442 passed, zero skipped, and also passed the hosted `gate` and `python-312-compat` jobs. The
main-only WSL security job was correctly skipped on the pull-request event; therefore the pull
request is proven as a candidate, not yet as the accepted production revision.

## What is already complete in code

The current tree already contains the production implementations for the earlier headline gaps:

- Canonical ASR is composed through `WslOmniAsrProducer` and the WSL worker, with exact OmniASR
  model/tokenizer identities, dependency receipts, source snapshots, validator routing, and gap
  preservation.
- `VisualComposer` owns Path B: one extraction/index pass, top-50 retrieval, reranking to 5–10
  survivors, and VideoChat3 reads only survivors. Its GPU-heavy phases have explicit release
  ordering.
- Stage 4 supplies extracted JPEG frame bytes, not text-only visual descriptions, to the Gemini
  judge.
- TimeLens is wired through `run_pipeline`, uses the selected transcript slice as its query, shifts
  window-relative evidence to media time, and is closed after the phase.
- Host CPU, model-fetch, WSL-ASR, scanner, and the measured Windows CUDA environment have exact
  dependency identities. Release construction, fresh-wheel smoke, SBOM, provenance, GitHub OIDC
  attestation, and exact-gate binding exist.
- The benchmark and editorial-regression harnesses exist and fail closed when a real labelled set
  is absent. Face-centred tracking exists and labels its fallback honestly.

Those facts mean this feature is an acceptance-and-completion program, not a rewrite of the core
pipeline.

## Remaining acceptance gaps

### 1. Production revision promotion

The candidate is not merged into `main`. A protected-main push must run the exact gate plus the
main-only WSL-ASR security job. The release workflow and its first live attestation are also waiting
for an accepted `main` revision. A pull-request pass cannot stand in for those results.

### 2. Canonical ASR product evidence

The runtime and live VEX machinery exist, and historical evidence records a successful two-GPU WSL
acceptance. The accepted production revision still needs its own source-bound receipt and VEX
result. The 38-minute real Sorani source must be run from that accepted revision and the report must
show that one failed segment cannot discard successful work.

Accuracy remains a different question: `BLOCKED.md` #1 records that no authorised, licensed,
reference-transcribed Sorani set covering Hewlêr, Slemani, Mukriyan, code-switching, noise,
overlap, and named entities is available in the workspace.

### 3. Full product-path acceptance on the dual-GPU machine

Path B and TimeLens have real component measurements, and the 8-frame VideoChat3 capacity on a
3090 Ti is measured. The product path still needs one accepted-revision run that composes Stage 0
through delivery with the chosen 8-frame/1 fps operating point, actual survivors, actual keyframes,
automatic sentence anchoring, TimeLens, reframing, and the five-file delivery set. The 64-frame
blueprint ceiling cannot fit this hardware; D-143/D-185/D-186 record the measured constraint, so
the acceptance result must identify the configured operating point rather than hide it.

### 4. Human-labelled quality evidence

`bench.py`, `editorial_bench.py`, and `repurposing.py` implement the metrics, but the evidence set
does not exist. `PROGRESS.md` M7.2 requires 200–500 human-reviewed candidates for editorial
threshold tuning. The smaller 20-item floor is only enough for a judge-model promotion regression
and must not be reported as M7.2 completion.

### 5. Speaker-aware reframing

`diarization.py` provides DER and turn-boundary metrics; `ingest.py` deliberately records
diarization as absent; `OpenCvFaceTracker` follows a continuous dominant face, not the active
speaker. `BLOCKED.md` #4 requires acceptance of the gated CC-BY-4.0 pyannote repository and a token
in the deployment environment. Real multi-speaker footage and human reference turns are also
needed to measure the result. SAM 3/Molmo2 remain governed by `BLOCKED.md` #9 and must not be added
unless face-centred speaker tracking proves insufficient and the frozen registry is amended.

### 6. Confidential cloud acceptance

Both Developer API and Vertex adapters exist. The production rule in BLUEPRINT §3 is stricter:
full transcripts may leave the network only through paid Vertex with the required zero-data-
retention governance. The existing Developer key had a zero request quota for the pinned Pro model.
An accepted production result needs the real Vertex project, ADC/bearer route, billing, retention
confirmation, and a rights-cleared matching video. Secrets remain outside the repository.

### 7. Durable release acceptance

The release workflow is implemented and contract-tested but no accepted `main` revision has yet
produced the four-file release set and a verified GitHub attestation. A version/tag policy and
durable GitHub Release are not defined. Native WSL builds are source-hash and inventory bound but
are not bit-reproducible compiler outputs; the VEX records the current risk disposition rather than
claiming a vulnerability-free runtime.

## Autonomy boundary

AI agents can autonomously finish code, tests, workflows, deterministic measurements on available
hardware, evidence capture, release automation, and adversarial review. They cannot fabricate:

- rights or licence acceptance for gated data/models;
- a paid confidential Vertex project or its retention contract;
- human Sorani transcripts, dialect labels, editorial preferences, or sign-off;
- footage the owner has not supplied; or
- a product decision that amends frozen BLUEPRINT §7/§9.

The implementation sequence therefore finishes every autonomous prerequisite before requesting
the narrow human inputs, and every unavailable acceptance is reported as blocked rather than
silently replaced by synthetic evidence.
