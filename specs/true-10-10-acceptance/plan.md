# Plan — true-10-10 acceptance, autonomy-first execution

Research: `specs/true-10-10-acceptance/research.md`

Specification: `specs/true-10-10-acceptance/spec.md`

Impact map: `specs/true-10-10-acceptance/impact-map.md`

Approved-by: Hawa — 2026-08-15; autonomy-first ordering reaffirmed by Hawa — 2026-08-17

## Current anchor

- Working branch: `codex/visual-short-window-provenance`
- Planning anchor revision: `17f2fc722d5a572e5ce31f397afaa5678980a99c`
- Base revision: `4dbffa2585e50e60d4dcebf6c508699aac0a35ad`
- Draft pull request: #21
- Canonical local gate at the planning anchor: 2,525 passed, zero skipped, `VERIFY OK`
- Canonical Stage 1 evidence: the rights-cleared 38-minute source completed from the base revision;
  545 regions were retained, two gaps were recorded, and a reuse run preserved the raw artifact.
- Current code-solvable critical path: `BLOCKED.md` #22, the truthful representation of scenes
  that yield fewer than two frames at the measured 1 fps / 8-frame operating point.

The current branch is a candidate, not an accepted production revision. The hosted pull-request
checks, protected-main checks, main-only WSL security job, and final accepted-SHA reruns remain
authoritative even when a local run is green.

## Execution rules

1. Exhaust autonomous work before asking for credentials, licences, labels, or product decisions.
2. Work in one bounded unit at a time. Claim exact files before editing, write or refresh research,
   EARS criteria, caller impact, and tests, then run focused checks and the canonical gate.
3. Commit only explicit paths. Never use broad staging. Push only a green commit and require hosted
   checks for that exact SHA.
4. Treat every model, provider reply, checkpoint, media path, and filesystem object as untrusted at
   its boundary. Operational failures become bounded structured refusals; programmer failures stay
   visible.
5. Never guess a quality threshold or amend the frozen blueprint through code. When evidence cannot
   choose, prepare the experiment and decision packet, then stop that lane truthfully.
6. Never interfere with unrelated GPU jobs. Real-model measurements run only under an observed safe
   GPU lease and record exact environment, memory, timing, model, source, and artifact identities.
7. A task is accepted only when its focused tests, full gate, exact-SHA hosted checks, real evidence
   where required, and documentation all agree.

## Autonomous wave A — close the short-scene visual blocker

1. Finish local, pinned-model research for the still-image and two-real-frame input semantics of
   Qwen embedding/reranking, VideoChat3, and TimeLens.
2. Wait for a safe dual-GPU lease; do not pre-empt unrelated workloads.
3. Run the prepared real-model harness on the exact one-second and sub-500 ms counterexamples.
   Record processor grids, delivered frame count, timestamps, pixel/vector hashes, cosine direction,
   reranker scores, VideoChat3 output, peak CUDA allocation, post-close allocation, wall time, and a
   deterministic rerun.
4. Reject any representation that crosses a cut, invents time, silently pads/repeats frames, changes
   the declared interval, or causes a model to consume a different count than provenance reports.
5. Record D-242 selecting one policy from evidence. If no faithful representation works, implement
   an explicit named refusal rather than a fabricated success.
6. Add the immutable representation/provenance record, bind it to model metadata and embedding-cache
   identity, preserve ordinary-window bytes, and prove exact private-pixel cleanup.
7. Prove every planned scene is either indexed exactly once or reported as an explicit refusal;
   retain top-50 retrieval, reranking, 5–10 survivors, survivor-only VideoChat3, and sequential model
   release.
8. Run real-media acceptance at 1 fps / 8 frames, then update #22 and the related #17 evidence only
   to the extent the measurement proves.

Exit: the supported operating point can process or explicitly refuse every short scene without a
crash, stale cache reuse, false timestamps, hidden padding, or GPU phase overlap.

## Autonomous wave B — prove the complete no-cloud product path

1. Re-run the exact GPU dependency and hardware identity check.
2. Run Stage 0, canonical Stage 1 reuse, sentence indexing, Path A preparation, and composed Path B
   on rights-cleared real footage.
3. Prove retrieval limits and ordering from artifacts: one extraction per scene, top 50 maximum,
   exact reranker provenance, 5–10 survivor rule when enough valid results exist, and only survivors
   reaching VideoChat3.
4. Exercise automatic survivor selection, real keyframe extraction, bounded judge-request assembly,
   TimeLens query/grounding/fusion, face-aware reframing, captions, render, and atomic five-file
   delivery. Use a schema-valid persisted verdict only for the unavailable cloud response, and label
   that seam explicitly; do not present it as a live Gemini acceptance.
5. Record scene/window identities, chosen anchors, frame timestamps, memory-release order, exact
   delivery checksums, clip duration, caption/transcript equality, and structured refusal behavior.
6. Run cache-miss and exact cache-hit passes. Refuse mismatched source, representation, model,
   checkpoint, or policy identities.

Exit: AC-4 and the local portions of AC-5/AC-6 have current-SHA real-media evidence. The only Stage 4
gap is the honestly named live confidential provider call.

## Autonomous wave C — eliminate every remaining code-solvable P0/P1

Run independent adversarial passes in this order, adding a regression before each fix:

1. Pipeline composition and model lifecycle: lazy acquisition, phase close order, OOM/launch/I/O
   normalization, no billing replay, and no swallowed programmer error.
2. Media and transcript integrity: path containment, immutable canonical ASR, alignment/gap coverage,
   timestamp arithmetic, cut containment, stale-frame isolation, and bounded parsing.
3. Filesystem/concurrency: root identity, symlink/reparse/hardlink resistance, private staging,
   crash-safe resume, atomic non-overwrite publication, lock interoperability, and cleanup reporting.
4. Model/checkpoint supply chain: exact revisions, metadata trust root, verified-byte-to-loader binding,
   effective fairseq cards, full dependency inventories, VEX applicability, and final-path recheck.
5. Cloud/security boundaries: credential-file and ADC failures, redirect isolation, route allowlists,
   bounded response bodies/errors, strict JSON types, one billed request, and secret-free diagnostics.
6. Render/delivery/privacy: exact selected span, no trailing footage, caption equivalence, pixel-grounded
   keyframes, bounded temporary retention, correct QC semantics, and exact five-artifact publication.
7. Release: immutable exact-SHA source exports, independent builds, clean installed-wheel smoke on
   Python 3.11/3.12, exact dependency locks, SBOM/checksums/provenance, permission separation, and
   attested/uploaded set equality.

Use fault injection, boundary/property tests, targeted mutation of security guards, malformed model
outputs, concurrent subprocesses, and clean-install probes. Do not weaken tests or count a failure
for an unrelated lint/type error as coverage.

Exit: no reproducible autonomous P0/P1 remains; every resolved defect has a discriminating regression
and the full gate is green.

## Autonomous wave D — prepare all human-dependent acceptance kits

1. Sorani ASR kit: signed manifest template, licence/consent fields, audio/reference hash import,
   dialect/condition coverage report, leakage/duplicate checks, and exact benchmark command.
2. Editorial kit: deterministic sampling of 200–500 real candidates, blinded labelling schema,
   annotator guide, disagreement/adjudication fields, train/holdout split, and promotion-report command.
3. Diarization/reframe kit: gated-model provisioning preflight, licence attribution, multi-speaker
   manifest, reference-turn import, DER/boundary/crop metrics, and explicit fallback acceptance.
4. Vertex kit: project/location/billing/ADC/retention checklist, no-transport preflight, matching
   media/transcript manifest, bounded-cost smoke command, and redacted evidence schema.
5. Decision kit: one evidence-backed page for each unresolved semantic choice — #13 Latin `ř/ł`,
   #14 VAD-pause rule, #15 TimeLens relevance, #18 Path A BM25 query ownership, #9 SAM 3/Molmo2,
   and #21 champion-adapter licence. Each page presents consequences and the recommended option but
   makes no hidden choice.
6. Release kit: recommended version/tag, non-overwrite publication, rollback-forward procedure,
   attestation verification commands, and owner approval line.

Exit: human work is reduced to supplying or authorising assets/accounts and making named decisions;
no additional engineering discovery is required to begin the acceptance runs.

## Autonomous wave E — promote one immutable production candidate

1. Reconcile claims, decisions, blockers, progress, and evidence without rewriting historical facts.
2. Run the exact canonical gate from a clean committed tree.
3. Commit explicit paths, push the focused branch, and require all pull-request checks at the exact
   SHA. Resolve review findings without broad staging or force pushes.
4. Merge only through protected `main`; capture the merge SHA and required checks.
5. Because source changes invalidate the receipt, provision/revalidate the final main source snapshot,
   run the main-only WSL VEX job, and rerun the 38-minute failure-preserving ASR acceptance.
6. Re-run GPU readiness and the full no-cloud product path at the accepted main SHA.
7. Build the release candidate twice, perform clean 3.11/3.12 wheel smokes, and verify the complete
   unsigned candidate set. Do not create the final production tag until the human release decision.

Exit: one exact protected-main SHA has green local/hosted gates, current WSL/ASR/GPU/product evidence,
zero autonomous P0/P1, and a release candidate whose remaining blockers are exclusively human-owned.

## Human-input gate — only after waves A–E

Request one consolidated packet, not repeated interruptions:

1. Authorised, licensed Sorani audio with human reference transcripts, dialect/condition labels, and
   consent/redistribution terms.
2. Kurdish editorial labels for 200–500 candidates plus final editor sign-off.
3. Acceptance of the pyannote gated licence, an HF token supplied outside Git, real multi-speaker
   footage, and reference speaker turns.
4. Paid confidential Vertex project/location, billing, ADC access, approved retention posture, and a
   rights-cleared matching smoke video.
5. Decisions for #13, #14, #15, #18, #9, #21, and the production version/tag.

Secrets, tokens, and client media remain outside Git and evidence is redacted.

## Human-enabled completion

1. Import and validate the supplied Sorani corpus; run per-dialect/per-condition ASR and alignment
   benchmarks without aggregate-only reporting.
2. Run the 200–500-item editorial study, tune only on training data, verify the locked holdout, and
   obtain Kurdish editor approval.
3. Provision pyannote, implement/enable the production diarizer and active-speaker/face association,
   then measure DER, boundary error, crop stability, and speaker mistakes on real footage.
4. Run the paid Vertex smoke once through the approved confidential route and record model, route,
   request/cost identifiers, retention approval, and redacted result.
5. Apply the approved semantic decisions through their own researched/tested units.
6. Create the approved immutable tag, let the guarded release workflow publish and attest all four
   payloads, verify the public release independently, and exercise the rollback-forward runbook.
7. Run a final independent P0/P1 audit and build an AC-1…AC-12 acceptance matrix with residual P2/P3
   risks. Obtain owner and Kurdish-editor sign-off.

Exit: only this evidence permits a truthful 10/10 claim. Until then HawEdit may be a highly hardened,
single-user production candidate, but missing human/cloud evidence is not converted into a score by
test count.

## Stop conditions

- Stop a lane rather than guessing when the next action requires a credential, licence acceptance,
  client-data right, human label, frozen-blueprint amendment, or release approval.
- Stop publication on any failed gate, wrong SHA, dirty tree, missing attestation, unresolved P0/P1,
  or evidence/source mismatch.
- A blocked external acceptance does not block unrelated autonomous waves.
- The active goal remains open until waves A–E are exhausted and the consolidated human packet is
  delivered; it is not marked complete merely because a dependency is external.
