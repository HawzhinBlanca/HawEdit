# Plan — visual-short-window-provenance

Research: `specs/visual-short-window-provenance/research.md`

Specification: `specs/visual-short-window-provenance/spec.md`

Impact map: `specs/visual-short-window-provenance/impact-map.md`

Approved-by: Hawa — inherited from the explicitly approved
`specs/true-10-10-acceptance/plan.md` Phase 3 and the instruction to implement all autonomous
remaining work before requesting human input.

## Task 1 — choose from measurements

1. After the active long-form ASR run releases the GPUs, extract the real one-frame counterexample
   and two distinct in-scene frames without crossing its cuts.
2. Compare the eligible still, adaptive-real-frame, and declared-repeat representations through
   the real Qwen embedder/reranker and VideoChat3 processor/model path.
3. Record exact pixels, clocks, embeddings/scores/readability, model versions, devices, peak memory,
   and wall time. Reject any option that hides padding, changes the claimed interval, or crosses a
   cut.
4. Write a new ADR for the selected semantic policy before implementing it.

Exit: one evidence-backed policy, not a guessed minimum-frame constant.

## Task 2 — encode representation provenance

1. Add failing tests for AC-1 through AC-5.
2. Implement one shared immutable representation record at the frame boundary.
3. Derive model metadata and timestamp checks from that record.
4. Bind the full representation to embedding-cache reuse.
5. Preserve exact ordinary-window behavior and private pixel cleanup.

Exit: focused unit/adapter suites green.

## Task 3 — compose and fail visibly

1. Prove every planned scene is either indexed exactly once or named as an explicit,
   policy-justified refusal.
2. Preserve top-50 retrieval, 5–10 survivor policy, exact reranker scores, and survivor-only
   VideoChat3 input.
3. Ensure operational model failures remain structured and programmer failures remain visible.

Exit: composed and pipeline regressions green.

## Task 4 — real-media acceptance

1. Run the exact GPU readiness gate.
2. Execute the representative source at 1 fps / 8 frames on the accepted revision.
3. Verify cache misses then exact cache hits, short-scene accounting, survivor identities, phase
   close order, GPU memory release, and no stale pixels.
4. Continue through automatic selection and the local product path if a complete sentence is
   selected.

Exit: AC-6 proven by a non-overwriting evidence artifact.

## Task 5 — gate, review, and promotion

1. Run the exact canonical `bash scripts/verify.sh` gate.
2. Update `BLOCKED.md`, `DECISIONS.md`, `PROGRESS.md`, and focused evidence to match only measured
   behavior.
3. Commit explicit paths, push a focused branch, require exact-SHA hosted checks, and merge through
   protected main.

Exit: #22 is closed only after local and hosted evidence agree.
