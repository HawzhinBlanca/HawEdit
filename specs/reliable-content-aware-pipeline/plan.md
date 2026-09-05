# Plan — earn a top-grade HawEdit pipeline

Approved-by: pending human approval

Date: 2026-09-06. Basis: [research.md](research.md), inspected HEAD `508f986e9f0ed5745d9ff46a9bffb9413b8a5456` plus the recorded working-tree changes.
Status: proposed plan only. No feature is accepted or implementation approved by this document.

## The outcome

Feed HawEdit an eligible Sorani episode and a small editorial brief. It should identify distinct, worthwhile moments; preserve what the speakers actually mean; choose readable captions and sensible framing; render consistent media; recover safely from interruptions; and present exact final files for human approval. It should return fewer clips or a clear refusal when evidence is insufficient. It must not reach a clip quota by weakening meaning or quality requirements.

The product advantage is **publishable Kurdish clips with very little correction work**. This plan deliberately does not pursue feature parity with a SaaS editor. It keeps the existing model roles, local workstation, Python pipeline, DBOS/SQLite, FFmpeg, typed contracts and acceptance machinery.

“10/10” means full acceptance against an agreed, bounded product contract and sustained evidence. It cannot mean perfect results on every future video or immunity to hardware failure. My earlier 6/10 was a subjective desk assessment; it is not a baseline performance measurement. Completing implementation tasks alone will not earn a new rating.

## Scope and constraints

- Primary domain: long-form Sorani interviews, podcasts and news discussion; target delivery remains the project’s vertical clip contract. Evaluate mixed dialects, code-switching, named entities, quiet speech, overlap, close-ups, wide shots and listener cutaways.
- Preserve BLUEPRINT §1 canonical raw speech and model roles, §3 independent discovery and sentence-hard boundaries, §4 Kurdish invariants, §5 contracts, §6 local deployment, §7 model controls and §8 independent evaluation.
- Keep OmniASR/CTC, the existing validator, Qwen retrieval/reranking, VideoChat3, Gemini editorial judging and TimeLens in their current roles. No model upgrades are approved here. Use existing applicable ADRs, including D-260 for the adapter route; resolve BLOCKED #21 before a new licence/production claim.
- No music/B-roll/animation program, invented footage, general timeline UI, social scheduling, service decomposition, second orchestration framework, distributed database or automatic model switching.
- Retain existing human QC. Automation proposes and verifies; the human owns publication approval. A model cannot approve its own output or impersonate a reviewer.
- Existing options and new uncommitted work are inventoried first. Preserve unrelated work; do not revert or silently overwrite it. One writer, sequential work, no parallel agents on this host.

## What would justify 9.5 and 10

All values below are **proposed acceptance targets**, not measured results or claims of universal standards. Phase 0 locks definitions, sampling and thresholds before the holdout is opened. No threshold may be loosened after seeing a failing holdout without recording a new protocol and evaluating fresh data.

| Dimension | Proposed acceptance bar | Evidence and protection against gaming |
|---|---|---|
| Technical reliability | At least 99% lower one-sided 95% confidence bound for successful technical processing of eligible jobs. No silent success, corrupt public bundle, unauthorized promotion or duplicated public delivery in the fault matrix. | Pre-register eligible inputs and faults. Count technical failures even when safely refused; report correct policy refusals separately. No “reliable because it rejects everything” score. |
| Meaning and boundaries | Zero observed critical meaning reversals, incorrect attribution or word truncations among released holdout clips; require an upper one-sided 95% bound on the critical-error rate below 1% before a population claim. | Kurdish reviewers examine original context and output; report candidate and released-clip errors separately. Cluster by episode/speaker; correlated clips do not count as independent trials. |
| First-pass usefulness | At least 95% of eligible proposed clips judged publishable without corrective editing, with a reported interval; at least 90% lower confidence bound. | Include every proposed clip under the locked selection policy. Record rejects, no-clip episodes and recall so cherry-picking cannot inflate precision. Exclude discretionary restyling from correction, but not subtitle, meaning, framing or audio repairs. |
| Discovery | Human-labelled candidate Recall@20 at least 90% overall, with per-path and per-condition reporting; no supported critical stratum hidden by the average. | Use BLUEPRINT §8.2 labels, shared episode windows, genuinely independent Path A/B inventories and an episode holdout. Treat the target as provisional until pilot establishes annotation feasibility. |
| Visual and subtitle quality | At least 98% of annotated relevant speaking time either correctly framed or in an explicitly acceptable neutral/source composition; all tested caption cues retain intended Sorani text and joining with no unsafe-area clipping. | Identity-aware human labels plus independent frame checks. Safe neutral composition counts separately from speaker tracking; face presence and textured backgrounds cannot satisfy identity/text claims. |
| Timing and sound | No word intersections by approved cuts; mapped A/V and cue timing within the declared tolerance (initial target: one output frame for A/V drift and 150 ms p95 word-highlight error on manually aligned words). Existing delivery loudness/peak contract passes after encode. | Rational media clock, independent decoded checks, human listening for pumping, clipped consonants and damaged speech. Timing targets require calibration; do not infer phonetic correctness from CTC confidence. |
| Operator effort | Median corrective editing time zero; p90 no more than one minute for a clip up to 90 seconds. Full review/watch time reported separately. | Time the same review protocol; include failed attempts and edits. This does not promise a one-minute end-to-end run or waive human review. |
| Comparative result | Blind preference at least 60%, with the lower 95% interval above 50%, against each tested OpusClip/Submagic/Klap configuration on eligible matched content. | Pair by source, randomize labels/order, account for episode clustering and multiple comparisons. Competitor non-support is an eligibility/coverage result, not a fabricated visual-quality loss. |
| Cost and runtime | Per-source-hour p50/p95 and cost per accepted clip within owner-approved budgets; recorded before/after on the actual workstation. | Set budgets from pilot measurement, not invented estimates. Include rejected candidates, retries, review and all model/CPU/GPU work. |

Statistical caution: for an ideal independent binomial sample with zero failures, approximately 300 trials are needed to bound a failure rate below 1% at one-sided 95% confidence. Repeated runs of the same episode cannot justify that population claim. Use a predeclared cluster-aware design and sample-size calculation; if the evidence is too small, report “not yet established.” The existing 200–500-candidate kit is a starting asset, not an automatic certificate.

**9.5 eligibility:** all critical safety/correctness gates, the locked target scorecard and exact-SHA required CI pass on the supported domain, with owner/Kurdish-editor sign-off. **10 eligibility:** the same bar holds on a second fresh episode holdout and a proposed 30-day representative use window, with recovery/rollback drills and no unresolved release-blocking defects. Maintain a comparison against a commissioned Kurdish editor: require non-inferiority within a pre-registered five-percentage-point publishability margin before claiming editor-grade results. A “better than editors” claim needs its own superiority evidence.

The human editor study and competitor paid runs are later execution decisions with explicit budget/authorization; this plan does not initiate them.

## The decision loop

Use one explicit loop throughout the current pipeline:

1. **Observe:** canonical words, alignment/gaps, source timestamps, scene boundaries, VAD, speaker turns and existing visual evidence.
2. **Propose:** existing judge suggests source-linked candidate spans, context needed, payoff and why the moment matters.
3. **Constrain:** deterministic policy protects speech, context, speaker attribution, allowed transformations and budget.
4. **Plan once:** resolve clip membership, retained source intervals, layout, cue text/timing and effective settings into versioned immutable data.
5. **Render and inspect:** encode the plan, then check actual files with independent tools and explicit limitations.
6. **Review and promote:** the human reviews an immutable candidate; publication promotes exactly its approved bytes.

Example: an answer beginning “No, that is not what happened” is not automatically a good standalone hook. Attach its question/context by canonical sentence IDs, preserve a following qualification, and let the judge assess the expanded passage. If the camera shows the listener, keep an honest source/neutral composition rather than claiming the visible face is the speaker. A pause before a difficult answer may carry meaning; leave it unless both audio and editorial evidence support removal. No invented line is inserted to repair missing context.

## Phase 0 — establish an honest baseline and lock the contract

**Purpose:** ensure work targets real defects on the actual serving path.

- Inventory all existing specs/ADRs/helpers related to this plan. Record “defined,” “called,” “rendered,” “independently checked” and “human accepted” separately; do not create a second task ledger for features already accepted with valid evidence.
- Resolve the recorded dirty tree through the owning task/user's existing authorization; do not overwrite it. Record exact baseline commit, file hashes, enabled options, model manifests, adapter digest, host/OS, GPUs/drivers, Windows and WSL Python/dependency versions, FFmpeg/library/font hashes and cloud endpoint/model IDs.
- Recheck live CI/runner state and BLOCKED #4, #13–#15, #18, #21 and #24. The old runner status is not current evidence. #24's recorded 2026-09-08 expiry is a concrete release review dependency; hash rebinding does not renew human security review.
- Use existing corpus/editorial/diarization acceptance tools. Partition by episode, speaker and source program before tuning; freeze training, development, acceptance and challenge assignments. Cover clean and noisy inputs, off-screen speakers, listener reactions, mixed languages, variable frame rates and no-good-clip episodes.
- Run the canonical gate and record failures honestly. Baseline the current rendered outputs and correction time. Lock the proposed targets, error taxonomy, sample design and resource budgets with the owner.

Exit: a reviewable baseline and evaluation manifest; no unsupported production or benchmark claim. Proposed tests: `test_acceptance_split_has_no_episode_or_speaker_leakage`, `test_scorecard_counts_refusals_and_all_proposed_clips`.

## Phase 1 — trust the artifact and retain it for review

**Purpose:** remove false positives and make the happy path finish without rerender workarounds.

1. Introduce explicit candidate states using existing run/report/bundle types: draft, rendered-for-review, rejected, approved, published, failed. Proposed names are design intent, not existing APIs. Keep unapproved candidates in a separate private, durable review location with bounded retention and safe cleanup.
2. Retain final-encode bytes and measurements before review. Approval binds the media hash, edit-plan/config hash and source identity. Promotion verifies again and publishes those exact files without invoking the renderer. Any material edit creates a new candidate and invalidates approval.
3. Reuse existing `QcRecord`, `Qc`, agent proposal/approval boundary and trust conventions. Explicitly validate approval verdicts. Treat self-reported watch time as metadata, not proof; correct “signed” wording unless actual authenticated signing exists. Do not add a new signing service by default.
   Audit `proposals.render_boundary_revision` and `render_caption_revision` alongside the canonical pipeline: both must invalidate old QC and converge on the same verification/promotion boundary. Never update a previous approval's hash to new render bytes. A rejected QC record must remain rejected when parsed by the CLI.
4. Separate render intent, measured observations and human findings. Verify all claimed reframe modes, final output frame rate, decoded duration, sidecar clocks, actual file set and caption events. An unsupported/unknown measurement cannot pass as true.
5. Replace caption texture-as-proof with checks tied to expected text and placement: canonical cue equality, glyph coverage/shaping goldens, per-cue expected geometry, and differential checks against a matched caption-free render at selected frames. Differential evidence can prove overlay presence/geometry, not linguistic correctness; retain human reading of Sorani holdout clips. Avoid OCR as a new dependency or sole oracle.
6. Prove that a no-caption textured background, wrong text, reversed joining, off-screen cue and undersized cue fail the appropriate checks. Validate final-compressed output; tolerate codec artifacts through calibrated comparisons, not assertions copied from the renderer.

Exit: unreviewed bytes never appear as public success; approved bytes publish once; known bad-caption and false-speaker cases cannot pass under an unrelated proxy. Tests: AC-01–AC-07 in `spec.md`.

## Phase 2 — one clock and one effective configuration

**Purpose:** prevent correct local features from disagreeing when composed.

- Resolve content type, preset, defaults and explicit flags once into a typed effective configuration. Explicit user choices have documented precedence; incompatible combinations fail before model/GPU work. Record the resolved values and policy version.
- Extend/reuse `SilencePlan` and existing timeline helpers for one source-to-output mapping. Distinguish source time, clip-relative time and rendered time in types; use rational frame rates at boundaries and avoid chained float rounding. Cover VFR by actual timestamps or one explicit normalized timebase with provenance.
- Derive ASS, SRT, EDL/OTIO, crop events, shot boundaries, hook/payoff markers and measurements from the same retained-interval mapping. Reconcile every delivered sidecar against the MP4. Do not export one continuous EDL span when the MP4 contains removed intervals.
- Restrict silence removal to confidently non-speech audio outside protected word margins and semantic/visual beats. An alignment gap is unknown evidence, not permission to cut. Keep quiet speech, laughter, breaths that carry meaning and turn-taking pauses by default.
- Preserve the distinction between continuous camera movement and discrete cuts. A gradual push-in should not be “proved” by expecting a scene-change detector spike.

Exit: mixed frame-rate, trim and caption tests agree within the locked tolerances; no silent drift or inconsistent preset path. Tests: AC-08–AC-11.

## Phase 3 — content-aware selection using the existing judge

**Purpose:** extract a complete idea, not simply a high score or a visually busy moment.

- Keep Path A/B independent. Reuse `JudgeRequest`, `JudgeVerdict`, merged candidates and existing transcript identity. Add only the missing source-linked context: question/answer relation, referent/setup sentence IDs, claim/qualification/correction IDs, payoff span and protected beats. Version this contract through an ADR; the model cannot supply unverifiable timestamps or rewrite canonical speech.
- Use full-transcript discovery and scoped evidence for judging; respect existing token/frame budgets. Long episodes use verified coverage with overlap and stable sentence IDs; no silent truncation or omitted tail of the episode. Any change to BLUEPRINT's full-transcript requirement needs a separately reviewed ADR.
- Select only sentence-complete contiguous moments in this release. Expand for necessary question/caveat/context within budget and duration policy; otherwise reject. Keep noncontiguous/cold-open assembly behind its existing acceptance requirements.
- Apply hard eligibility rules before ranking: meaning fidelity, attribution, context, complete boundaries, alignment coverage and privacy rules cannot be compensated for by a high hook score. Use one ranking function for single and batch modes; stable tie-breaking makes replay deterministic.
- Run calibration through existing editorial acceptance tools using independent Kurdish labels. Measure false accept/reject, recall by path and condition, pairwise ordering and calibration uncertainty. Repeat judging only for ambiguous cases within a bounded budget; agreement is a diagnostic, not independent truth.
- Source speech, metadata and retrieved text are content, never executable instructions to the agent. Tests cover a transcript telling the judge to bypass checks or change settings. Bounded proposals cannot mutate canonical data, approve QC or publish.

Exit: unseen context-dependent candidates are expanded or refused; accepted clips preserve meaning and worthwhile coverage. Tests: AC-12–AC-15.

## Phase 4 — content-aware framing, captions and sound

**Purpose:** deliver readable, stable clips whose presentation serves the passage.

- Reuse `MotionSpeakerTracker`, diarization, face detection and shot boundaries. Reset spatial identity at cuts, track continuity within shots, account for camera motion, require actual evidence before naming the speaker, and distinguish visible listener/reaction shots from active-speaker shots. An off-screen speaker is a valid state.
- Use a shot-level policy: stable close-up when confidence supports it; deliberate source/neutral framing for ambiguity or meaningful reactions; existing two-person layout only when both subjects are reliably located and the layout improves the content. Apply hysteresis/dwell to avoid jitter. Do not force split-screen or zoom on every clip.
- Adapt crop to face/body geometry, source resolution and legibility constraints. Evaluate opening, transitions, extremes and ending. Avoid upscaling beyond an accepted quality bound; preserve source composition when a vertical crop would destroy necessary content.
- Use shaped text width, actual font coverage, phrase boundaries, reading exposure and safe display regions to compose captions. Start with one owner-approved restrained style. Preserve verbatim Sorani and protected names/code-switch spans; highlighting must not split joined graphemes. Do not set a universal characters-per-second rule from English guidance.
- Reuse audio analysis and two-pass output normalization. Measure before deciding whether conditioning is useful; compare bypass against conditioning on speech quality. Normalization and denoise/de-ess are different operations. Any change to D-264's current mandatory chain needs an ADR and listening evidence.
- Store reasons for layout/caption/audio decisions in the existing report. Permit a constrained per-candidate correction through existing revision tools; no large editor UI is required.

Exit: annotated speaker/listener scenes, noisy/clean audio and mobile caption cases meet the locked scorecard on rendered outputs. Tests: AC-16–AC-18, plus human acceptance protocol.

## Phase 5 — connect episode planning and prove recovery

**Purpose:** finish the useful work once, even when a run is interrupted.

- Wire the existing episode selection into actual rendering using shared eligibility/ranking and one ingest/transcript/index pass. `N` is a ceiling. Publish no duplicate/overlapping ideas just to fill it. Require actual text evidence for diversity and distinguish lexical overlap from semantic duplication.
- Each candidate owns its immutable plan and six-file bundle under D-263. An episode manifest records selected, rejected, failed, pending-review and published items without claiming all succeeded. Resume only missing work; preserve successful bundles. Final episode publication points only to independently validated approved bundles.
- Retain D-A3's coarse DBOS step and SQLite initially. Inventory each expensive/artifact-producing/billed boundary and test current cache recovery. Add a narrowly scoped checkpoint only where measured recovery loss warrants it; changing durability granularity requires an ADR and workflow-version migration plan.
- Version cache identity with source bytes, canonical transcript/adapter/model revisions, normalization, prompt, policy, effective configuration, font/filter/encoder/runtime facts as relevant to each artifact. Invalidate dependent stages only. Do not cache mutable approval as model output.
- Bound retries, timeouts and total spend. Retry transient faults only; reject deterministic contract/integrity failures. Persist request intent and response identity for cloud calls. On an uncertain billed result, do not claim exactly-once or automatically resubmit without a defined bounded owner policy; use provider idempotency/reconciliation only when supported.
- Test crashes before/after artifact writes, cloud response persistence, render completion, human approval and public rename; also test duplicate submission, disk-full, malformed caches, GPU OOM, WSL failure and network interruption. Record exact verified child PIDs for test cancellation; never send Ctrl+C to Codex terminals or use a detached Start-Process verification launcher on this host.
- Preflight available bytes, source readability, weights/receipts, model route, GPU leases and budgets before expensive work. Preserve the primary failure, return structured actionable reasons and release resources on every path.

Exit: batch generation is observable end to end, failures remain visible, fault drills preserve accepted work and do not publish false success. Tests: AC-19–AC-22.

## Phase 6 — maintainability, release proof and ongoing quality

- Refactor only the seams touched above. Keep orchestration thin and side-effect adapters separate from pure decision/timeline logic. Prefer existing dataclasses/Protocols, strict validation and explicit result/error types over new generic frameworks.
- Validate external JSON once at the boundary; use typed internal objects. Eliminate contradictory flags, hidden mutation, overly broad exception swallowing and duplicated eligibility logic encountered in the changed paths. Do not rewrite all modules to meet arbitrary file-length or abstraction targets.
- Version persisted schemas and workflow code. Test reading supported previous artifacts, deterministic migration, cache invalidation and rollback. Preserve immutable accepted releases and their media; a provider upgrade cannot retroactively change a reviewed plan.
- Keep dependency/model/font hashes pinned and licences recorded. Revalidate current provider lifecycle at release time. Evaluate replacements in shadow on the frozen Sorani suite and a fresh acceptance slice; preserve owner authorization and an explicit rollback route. “Future-proof” means controlled change, not automatic upgrades.
- Follow the exact canonical gate, real-media tier and required exact-SHA CI. Before editing enforcement surfaces, create the required visible `.codystem-allow-self-edit` marker. Only the ledger tool may flip rows after qualifying evidence; CI remains mandatory.
- Run independent blind comparison tracks: (a) full episode-to-clips with each system's supported input and equal review allowance; (b) finishing quality on matched source spans so discovery does not confound presentation. Record platform/version/plan/settings/date, failures, manual edits, all costs and exported media hashes. Do not upload private footage without explicit authorization for that destination.
- Reuse existing reporting/acceptance tools for a compact release report: supported domain, scorecard, per-condition misses, refusal/coverage rate, resource use, reference manifests, accepted commit and remaining human decisions. Do not let the generator supply its own final score.
- After acceptance, repeat a small regression sample on dependency/prompt/policy changes; periodically refresh a separate blind set. Preserve old holdouts as regressions but stop calling them unseen once they influence tuning. The proposed 30-day use window is a later acceptance activity, not an automation created by this plan.

Exit: all required acceptance evidence and owner/Kurdish-editor sign-off are present; only then consider a scoped 9.5/10 or 10/10 assessment. Tests: AC-23–AC-24 and the human/real-media scorecard.

## Execution order and change discipline

Use [tasks.md](tasks.md), [spec.md](spec.md) and [impact-map.md](impact-map.md). All tasks are proposed and unchecked. Phase 0 starts first; artifact truth and review must precede expanded automation. Label collection can proceed independently outside this checkout, but implementation remains sequential on this machine. Batch and runtime tests reuse the stabilized plan/clock; no broad refactor precedes behavioral proof.

For each approved task: refresh symbols/references with Serena, add a meaningful failing regression, make the smallest change, run `bash scripts/verify.sh`, review actual media where relevant, then use `scripts/update-ledger.sh` only with named tests from that run. Required CI at the same committed SHA is the final acceptance condition. Do not skip failing tests, weaken goldens, edit the count floor or hand-write `.gate` artifacts. A gate failure is work to resolve, not a reason to change the grading command.

No completion date is promised before Phase 0 establishes baseline runtime, test duration, corpus readiness and the human label budget. The first approved milestone is small: reproduce the false-caption/false-speaker paths and retain exact review candidates. There is no need to wait for a new model or decorative feature to begin that work.

## Owner inputs at the point they are needed

1. Approve this plan's bounded scope and proposed scorecard before implementation; record approval on this file rather than assuming it from the research request.
2. Phase 0: confirm supported dialects/content conditions, nominate Kurdish reviewers, and lock cost/runtime/review-effort budgets from the measured pilot.
3. Before gated runtime/production evidence: resolve applicable existing BLOCKED items and current CI runner/security review requirements. Reuse prior valid authorizations; do not ask again merely because a task changed.
4. Before comparative external runs: approve actual source material, destination and spending. Missing competitor support narrows the comparison claim; it does not block local pipeline repair.

The next implementation action, after plan approval, is T00: freeze the baseline and acceptance protocol on the current actual checkout.
