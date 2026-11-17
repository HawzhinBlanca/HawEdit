# Acceptance Mathematics And Evidence Research

2026-10-02; baseline HEAD 372a16645d7a8558bc6cedcff34a9fbfa13f712f plus uncommitted
source package 510bfb7e333b7210cf6fd252cc26a7b22cb9ffd63b9d1b744f2527830ccac65a.
Grounding: BLUEPRINT sections 8.1-8.3 and the approved frozen release thresholds in plan.md.
Serena now has 151 actual definition/reference records. No scorecard/comparison source
was changed during this research or the concurrent, source-frozen T4 full gate.

These are deterministic synthetic counterexamples against actual public helpers, not human
evaluation, model inference, benchmark results, paid work or release evidence. CPython 3.12.10
on the recorded Windows host; stdlib arithmetic/random/JSON and current HawEdit source.
Hardware inventory in readiness.md is historical provenance, not a performance measurement.

## Confirmed Defects

1. analyze_study computes hook_mean_diff from cumulative wins rather than paired option
   scores. The same two ratings yield 2.5 in one order and -0.5 in the other. Clarity and
   shareability fields are means of a single overall rating, not system-minus-human differences.
   PairRating lacks per-option scores, so correct differences cannot be recovered by changing
   the averaging line. See comparison-counterexample.json; source comparison_kit.py.
2. Repeating one identical reviewer submission on one pair 200 times returns a 0.9812 lower
   bound and better_than_a_team=true. The helper pools repeated ratings as independent trials,
   does not reject duplicate reviewer/pair identity, and has no episode-cluster identity in its
   input schema. That diagnostic is not evidence of superiority. Episode/reviewer dependence,
   missing observations and ties require a frozen estimand/method before any real evaluation.
3. BlindedStudy.to_dict exposes the random seed. Native prepare_blind_study copies four real
   existing fixture pairs; reconstructing Random(seed) from the public item order recovers
   the entire private A/B role map. unblinding_key.json also lives beside the public manifest
   without access-control sealing. See blinding-counterexample.json. No commissioned editor
   comparison took place; matching roles demonstrates an information leak, not quality.
4. compute_visual_scorecard accepts malformed SHA/date text, supplied signoff strings and
   arbitrary competitor interval fields. evaluate_leadership_claim accepts 10/10 for a synthetic
   200-proposal, 20-episode card with only 80% accepted and visual relevance 0.2. The first-pass
   interval is 0.7391-0.8495, below the approved release lower bound; no signed evidence or
   30-day sustained acceptance exists. See scorecard-counterexample.json. target config fields
   are not sufficient enforcement, and is_release_eligible only checks basic count accounting.
5. The visual CI uses a normal 1.96 cluster residual margin widened by naive proposal-level
   Wilson bounds. This is not validated small-cluster/repeated-reviewer inference. Empty
   speaker/media split identities are accepted, and episodes in the registered split with
   no proposals are absent from computed episode counts. These last points are inspected
   source facts, not a statistical coverage experiment or a measured human acceptance rate.
6. export_to_qc_records fabricates seconds_watched=60 and infers pass from a preferred option.
   Preference is not authenticated native-editor fidelity review; unknown pairs are skipped.
   Do not allow this export to authorize delivery. This is static inspection, not a publication.

## Required Repair Before Evaluation

Keep the existing kits, but add a versioned, integrity-bound study schema with registered
episodes/speakers/media, per-option ratings, authenticated reviewer identity, explicit missing/
duplicate/adjudicated outcomes, correction time and actual viewing evidence. Keep the private
randomization material outside the reviewer package; do not publish its seed or accessible key.
Freeze the corpus, assignment, holdout and statistical plan before collecting outcomes.

Preserve every proposed/refused/rejected/no-clip episode in accounting and report appropriate
separate clip-level and episode-level estimands. Derive competitor metrics from verified raw
observations, not supplied CI fields. Validate all provenance against actual signed artifacts,
current source/configuration and applicable CI. Require the complete frozen thresholds,
AC-1-AC-12, sustained use and owner/editor authentication before any 10/10 authorization.

Use established, independently checked clustered/repeated-observation methods; the exact
choice needs methodological research and a preregistered ADR, not an ad hoc repair justified
by synthetic success. Audit coverage under relevant cluster sizes/imbalances and boundary
rates using reproducible simulations as supporting math evidence, never as human study data.
Wilson intervals may remain explicitly labelled independent-proportion supporting summaries.
Do not lower thresholds after seeing a holdout or add artificial observations to reach them.

Native regressions must cover order invariance, duplicate submissions, cluster/reviewer
dependence, public-seed unblinding, missing identities/no-clip episodes, bogus provenance/
signoff, fabricated comparator bounds and preference-to-QC escalation. Source/caller maps
and an approved task plan precede edits; this research is not a completed scorecard repair.

## Current-Package Reproduction

2026-10-03 local / 2026-10-02 UTC. acceptance_current_probe.py executes the actual public
scorecard helper against deterministic synthetic input. T8-current-scorecard-counterexample.json
binds this new observation to current package 6bde42cba644a4510bbdb1bdd28596dba7cece5c328612c6dcbcb0e3d7f0b2cb
and native CPython 3.12.10, not the historical source above. The helper still permits a
10/10 label for 160/200 accepted synthetic proposals across 20 synthetic episodes, first-
pass lower bound 0.7391448134346212, visual relevance 0.2, malformed SHA/date and unsigned
sign-off strings. Deliberately inconsistent supplied competitor bounds are not derived
from observed ratings. This is a reproduced admission defect, not human/model evaluation,
superiority, published media or any accepted verdict. No threshold or source is changed.

Fresh acceptance_serena.py / serena-T8-current-map.json records the actual scorecard and
comparison definition/caller topology for the next repair. A scoped approved implementation
unit and explicit caller/test compatibility still precede source edits. First block unsupported
claim authorization and preference-to-QC escalation; descriptive synthetic accounting cannot
stand in for authenticated release. Choosing and validating the clustered/repeated-reviewer
method remains separate preregistered research, never a post-holdout threshold adjustment.

## Flag-Only Acceptance Admission

2026-10-03 local. Actual read of editorial_acceptance.py shows _verify_signature uses
bounded bound-byte snapshots and OpenSSH namespace/key fingerprint verification. Its
signed study evaluator is distinct from the public scoped/sustained helpers. Those latter
helpers accept booleans instead of reopening authenticated gate/CI/reviewer evidence.
evaluate_scoped_acceptance accepts any nonempty SHA of length at least seven and can
set accepted despite the invalid-SHA deficiency. evaluate_sustained_acceptance similarly
accepts supplied verified/signoff flags and a claimed day count; it does not observe a
real use interval, reopen the fresh holdout, or enforce the frozen quality thresholds.

acceptance_flags_probe.py executes those actual public APIs. Its immutable
T8-flags-admission-counterexample.json binds the observation to its actual package digest,
HEAD and CPython version. All 200 synthetic proposals are refused, zero are accepted,
all 20 claimed episodes produce no clips, commit_sha is "not-a-sha", and no independent
human/gate/CI/sustained evidence is supplied. True flags still yield scoped accepted and
sustained sustained with a 10/10 string. This is admission-defect evidence only, not a
human study, accepted release, elapsed use window or authorized score. No implementation
claim about those helpers follows from the paired-data unit. Their repair remains mandatory.
