# Plan — true-10-10-acceptance

Research: `specs/true-10-10-acceptance/research.md`

Specification: `specs/true-10-10-acceptance/spec.md`

Impact map: `specs/true-10-10-acceptance/impact-map.md`

Approved-by: Hawa — 2026-08-15

The owner approved the roadmap in this task. Work proceeds in dependency order. Each task is the
smallest independently reviewable unit, is test-first where code changes are needed, runs the exact
canonical gate, updates the ledger only through `scripts/update-ledger.sh`, commits explicit paths
only, and then waits for required hosted checks before its acceptance claim.

## Phase 1 — establish the production revision

1. Commit this acceptance package on the already-green PR branch.
2. Run `bash scripts/verify.sh`; push only after it passes.
3. Require PR #2's exact hosted checks to pass at the new SHA.
4. Merge through the repository's protected non-force path.
5. Capture the accepted `main` SHA and its required checks. Any main-only WSL failure becomes the
   next task; it is not bypassed or relabelled.

Exit: AC-1 is satisfied and one immutable accepted SHA anchors every later artifact.

## Phase 2 — canonical ASR acceptance

1. Provision or reuse only a receipt valid for the accepted SHA.
2. Run the live WSL VEX gate and retain its non-overwriting evidence artifact.
3. Execute Stage 1 on the rights-cleared 38-minute Sorani source.
4. Audit successful segments, failed gaps, validator/adapter provenance, timings, GPU identity, and
   transcript integrity. Add regressions for any code failure before rerunning.
5. Import an authorised labelled corpus when supplied, then run the per-dialect §8.1 benchmark.

Exit: AC-2 and AC-3 are satisfied. AC-7 remains blocked until human-reference data exists.

## Phase 3 — complete dual-GPU product-path acceptance

1. Run the exact GPU dependency/hardware readiness check.
2. Execute the full local visual path at the measured safe operating point; record window/fps,
   counts, survivor ordering, VideoChat3 inputs, phase close order, peak allocation, and timings.
3. Execute automatic selection, actual keyframe judging, TimeLens fusion, reframe, captions,
   render, and atomic delivery on real footage.
4. Adversarially verify structured failures, no stale pixels, no model overlap, no path escape,
   bounded diagnostics, one billed call, and exact delivery bytes.

Exit: AC-4, AC-5, and AC-6 are satisfied on the accepted revision. Quality judgments remain for
Phase 4.

## Phase 4 — quality evidence and threshold promotion

1. Validate licences, consent, coverage labels, and manifest integrity for the Sorani corpus.
2. Produce per-dialect/per-condition ASR and alignment results.
3. Assemble 200–500 real candidates with blinded human labels.
4. Run the editorial benchmark, analyze path-unique wins and failure slices, tune only thresholds
   justified by the labelled set, and preserve a locked holdout.
5. Obtain Kurdish editor approval of the report and representative outputs.

Exit: AC-7 and AC-8 are satisfied. This phase requires owner-provided or owner-authorised data and
human review; automation prepares, validates, measures, and reports it.

## Phase 5 — speaker-aware reframing

1. After gated access is accepted, provision the exact pyannote production and control models with
   licence attribution and authenticated identities.
2. Implement the production diarizer adapter and Stage 0 structured-failure path.
3. Reconcile exclusive turns to aligned words and pass eligible turn bounds into Stage 5.
4. Associate active speakers with detected faces; preserve explicit fallback when ambiguous.
5. Measure DER, boundary error, crop stability, and missed/incorrect-speaker crops on labelled real
   multi-speaker footage.
6. Decide from evidence whether SAM 3 is necessary; do not add it before the §7 decision.

Exit: AC-9 is satisfied, or remains explicitly blocked on gated access/data/registry decision.

## Phase 6 — confidential Vertex acceptance

1. Validate the paid Vertex project/location, ADC route, allowlisted endpoint, and approved
   retention policy without persisting credentials.
2. Run no-transport refusal controls, bounded cost/token checks, and one-call accounting.
3. Run the rights-cleared live smoke with matching pixels/transcript.
4. Record request identifiers, model/version, project/location, cost, retention approval, and
   redacted logs. Compare against the Sorani regression set before promoting a new model.

Exit: AC-10 is satisfied. Human/cloud-account governance is required.

## Phase 7 — production release

1. Define and record version/tag and rollback policy.
2. Trigger release only from the exact accepted main gate.
3. Verify fresh 3.11/3.12 wheel installs, all CLIs, bundled data, SBOM, checksums, and provenance.
4. Verify every GitHub attestation using the exact workflow, source ref, source digest, signer
   digest, and hosted-runner policy.
5. Publish a non-overwriting GitHub Release and exercise install/rollback instructions.

Exit: AC-11 is satisfied.

## Phase 8 — final adversarial and human acceptance

1. Run a fresh independent P0/P1 audit across ingest, ASR, discovery, judgment, boundary, render,
   delivery, provisioning, cloud, and release surfaces.
2. Resolve every code-solvable P0/P1 and rerun its adversarial regression plus the full gate.
3. Build an acceptance matrix linking AC-1…AC-12 to immutable evidence.
4. Record all residual P2/P3 limitations and operator runbooks.
5. Ask the owner and Kurdish editor to sign only after every human-owned criterion is evidenced.

Exit: AC-12 is satisfied. Until then the project may be excellent and release-candidate quality,
but it is not truthfully rated 10/10.
