# Reliability first, then earned creative quality

Date: 2026-09-09. Research SHA: `532e6efb1708e8dc2c3d14dde4fb7927f5115006`.
Approved-by: pending for new implementation proposed here. Existing authorizations remain valid.
Status: proposed work; this audit implements none of it.

The target is an autonomous director for faithful, watchable speech highlights and story cutdowns. Do not expand timeline editing, music, effects or presets. Do not start with a framework rewrite or a larger model fleet. Reuse the existing transcription, alignment, discovery, judge, assembly and delivery code after fixing their contracts.

## The top three work packages

### 1. Make completion trustworthy and recoverable

First, connect `web.py` to real source registration and the real pipeline. Give each accepted source a digest and each request a durable unique job ID. Distinguish idempotent retries from distinct jobs. The UI should reflect persisted stage events and display only that job's manifest-bound results. A demo sample is an example, never the result of an unrelated source.

Then make failures ordinary supported outcomes: invalid input, corrupt media, model unavailable, insufficient disk, worker stopped, network timeout, ambiguous billed call and output rejected. Every job must eventually have an understandable terminal or actionable state. Queue work with bounded concurrency and leases. Use the existing recovery abstractions where appropriate, but verify that the live execution path actually consumes them.

Checkpoint identity must cover source, effective settings, model revisions, schema/code version and produced artifacts. Before reuse, check output digests and decodability. Invalidate only dependent stages. Persist successful external calls before advancing; reconcile uncertain calls instead of blind retries that may rebill.

Exit evidence: distinct-source API/UI test, rapid-submit uniqueness, restart recovery, actual failed-job UI, corrupted-cache invalidation and candidate-two playback. Never manufacture a “completed” event without a validated final manifest. This fixes R1, R5, R6 and R8.

### 2. Make one plan control every byte delivered

Repair assembly before adding editorial sophistication. Preserve source Word IDs, exact source ranges and ordered output ranges. Keep source time and output time explicit in types. Carry the complete assembly object/map into judging and rendering; never replace it with one continuous source interval. Build caption text from retained source identities, not object identity of remapped words.

Construct the professional edit plan before rendering. It must specify the actual selected story, every retained span, ordering, joins, context dependencies, shot decisions and unresolved uncertainties. All captions, rendered trims, EDL, review package and final manifest derive from that same versioned plan. A post-render descriptive sidecar is insufficient.

Extend the delivery bundle deliberately under D-263. Stage the mandatory plan, measurements, source/output hashes and all required media/sidecars together; validate them; publish once. Do not copy optional unvalidated files into a published bundle. A reported failure must not conceal a published artifact. On restart, reconcile a completed atomic commit to the correct job state.

Exit evidence: a real two-span and three-span video containing visibly/audibly different source segments; correct sentence text, source IDs, audio, captions and provenance at every join. Verify cold-open order and silence-removal combinations. Inject write/rename failures and terminate an isolated worker at publication boundaries; after restart, there must be either a coherent complete package or an explicit recoverable private attempt. This fixes R3 and R4.

### 3. Earn the director's judgment and the right to say “passed”

Start the benchmark before tuning. Separate development, calibration and held-out episodes by source/speaker where feasible. Include serious testimony, quiet hooks, late peaks, names/numbers, overlap, abrupt camera changes and weak source material. Keep episode 29 as a regression example, not evidence of generalization.

Use the full episode to form a source-backed story representation: speakers/entities, claims, events, chronology, cause, required context, setup/payoff and uncertainty. Produce several candidate paper edits for distinct purposes: standalone moment, coherent story cutdown, or honest anthology. An anthology must not invent a causal connection between independent highlights.

Select with explicit competing constraints: why the viewer should care, complete meaning, strength of payoff, information density, natural speech and visual feasibility. Preserve qualifications and meaningful pauses; remove redundant verbal material only when the result stays faithful and natural. The system should abstain when the source cannot support a professional cut.

Independently inspect the rendered result and aligned source. Planned windows are not observations. Record real decoded coverage and audio evidence, then assess joins, context, attribution, subject retention, text obstruction and ending. A missing detector, missing source context, decode gap or stale hash is unknown/refused, never success. Use bounded repair, then rerender and remeasure the exact new bytes.

Collect expert Sorani editor judgments and target-viewer comprehension on blinded, randomized pairs. Compare the same source, purpose and duration constraints against professional editors and any chosen competitors. Keep ranking claims limited to the tested category and dataset. Do not select three products from marketing claims and call the result a benchmark.

Exit evidence: R2/R7 bypass probes fail closed; actual pipeline invokes inspection; experts prefer the outputs on unseen episodes; quality remains stable across repeated runs; no per-episode selection scripts or manually authored pass reports in the acceptance path. This addresses R2, R7 and R9.

## What earns higher ratings

These are proposed rating milestones, not guaranteed scores or current measurements.

* **5/10 reliability:** all reproduced release blockers resolved through the actual app; clean canonical gate and exact-SHA CI; recoverable errors and correct artifact identity demonstrated.
* **7/10 product:** unfamiliar inputs reliably produce faithful complete stories with natural speech and usable crops; paper edits and outputs match; no hidden manual selection.
* **9/10:** strong blinded editorial preference, publishable yield and low defect rates on an untouched, diverse set, plus recovery/soak testing under ordinary owner workloads.
* **10/10 aspiration:** repeated independent evidence of exceptional work on the declared task, dependable recovery and honest abstention outside its competence. It cannot mean perfection on every possible input.

## Proposed acceptance targets — agree before testing

For reliability, use an isolated worker and a fault matrix: missing/truncated input; corrupted proxy/audio; invalid provider JSON; timeout after request acceptance; model unload failure; disk/write error; crash before/after manifest publication; duplicate request; two workers claiming one job; config/model change on resume; missing returned artifact. Every scenario must produce correct recoverable state, no wrong-source result, no false approval and no overwrite of a completed delivery. Declare allowed retry and reconciliation behavior per fault.

For quality, initially aim for at least 90% of eligible tasks yielding a structurally publishable result without manual re-editing, at least 95% standalone comprehension among accepted outputs, and zero observed critical meaning/attribution failures. These are proposed decision rules requiring calibration, not external standards. Measure coverage of eligible tasks alongside quality so blanket rejection cannot game the metric. Report failure counts, denominators and uncertainty; zero observed defects is not proof of zero future risk.

Measure worst contiguous subject loss, audible splice defects per join, timestamp error, false approvals, recovery correctness, duplicate billing incidents, time-to-result and time-to-recovery. Define time/resource targets on this actual hardware from representative episodes; do not invent a latency promise before measuring.

## Implementation discipline

Map changed symbols/callers with Serena when available and update `impact-map.md`. Add EARS criteria and regression tests before implementation. Respect BLUEPRINT §2–§5, D-262 assembly correction, D-263 atomic delivery and D-266 timing behavior. New architecture/dependency/spec divergence needs an ADR. Extending the protected artifact/gate harness requires the project's visible self-edit process; do not quietly weaken checks or reference outputs.

Run the unchanged canonical gate after each implemented task, and required CI from the committed SHA. Do not mark rows complete from helper tests, coverage count, screenshots or this plan. Each task closes only with evidence from its real user-visible path.
