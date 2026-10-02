# Acceptance Authority Guard - T8 Sequential Unit

Approved-by: Wareen, inherited explicit implementation approval for the evidence-based studio plan.
Status: research/implementation unit, not release acceptance or a replacement for the seven-phase plan.

## Research And Boundary

Read the project vault checkpoint, AGENTS.md, parent plan, signed-study-adoption-research.md,
statistical-acceptance-research.md, actual source and tests. Existing actual Serena research
maps and the fresh authority guard map identify definitions and callers before edits.
The native flag and scorecard counterexamples demonstrate false authority, not human study results.
BLUEPRINT sections 8.1-8.3 and D-276 require actual evidence; D-263/D-274 delivery and episode
contracts remain unchanged. Blockers #1, #3, #4, #21, #24 and #25 remain external obligations.

The compatibility APIs accept aggregate counts, Boolean claims and reviewer names, not
the gate report, required hosted checks, signed independent observations or a use journal.
They cannot verify acceptance. This unit removes that false capability without inventing
a signature, substituting an unsigned evidence manifest, or choosing a statistical method.
Counts and diagnostics remain available; supplied claims remain explicitly self-reported.
The signed study and release approval verifiers retain their narrower existing contracts.

## EARS And Named Tests

- AG-1: WHEN callers supply flags, THE scoped intake SHALL refuse acceptance and identify
  missing independently verified evidence. `test_scoped_claims_cannot_authorize_acceptance`.
- AG-2: WHEN sustained-use counts and sign-off flags are supplied, THE sustained intake
  SHALL refuse acceptance, retain the request as unverified and emit no authorized rating.
  `test_sustained_claims_cannot_authorize_rating`.
- AG-3: WHEN claims have malformed types or lower the frozen sample/window floor, THE
  intake SHALL refuse them. `test_scoped_claim_input_validation`,
  `test_sustained_claim_input_validation`, `test_acceptance_floor_cannot_be_lowered`.
- AG-4: WHEN descriptive reports are manually constructed or altered, THE assertion
  helpers SHALL not authorize them. `test_report_construction_cannot_forge_authority`,
  `test_report_assertions_do_not_trust_status_fields`.
- AG-5: WHEN counts are directly constructed, THE scorecard SHALL validate accounting,
  finite values and episode consistency and label the unclustered reference uncertainty.
  `test_scorecard_direct_construction_validates_counts`,
  `test_aggregate_uncertainty_is_reference_only`.
- AG-6: WHEN visual scorecards contain supplied metrics or names, THE release/leadership
  helpers SHALL not authorize release or superiority.
  `test_visual_descriptions_are_not_release_authority`,
  `test_visual_report_labels_unverified_inference`.

## Caller Impact

`compute_acceptance_scorecard`, `AcceptanceScorecard`, scoped/sustained evaluators,
their report serializers/assertions: public `hawedit.__init__` exports, three existing
editorial acceptance tests and diagnostic probes. There is no production engine admission
caller. Existing signed-study CLI remains untouched. Preserve meaningful refusal/count
assertions; replace only tests that mistakenly equate supplied flags with verification.
`VisualScorecard.is_release_eligible`, `evaluate_leadership_claim`, `to_dict`: public exports,
one existing visual scorecard test, `compute_visual_scorecard` and diagnostic probes.
Preserve existing numeric/leakage/refusal assertions; strengthen the false-release expectations.
Fresh Serena mapping also covers each existing test changed by this unit.

## Sequential Implementation And Evidence

1. Freeze fresh actual symbol/caller mapping and add regressions; record genuine red run.
2. Repair only the descriptive/authorization boundary and label reference statistics.
3. Run all affected tests, native counterexample replays, lint/types and the exact full gate.
4. Preserve terminal logs, JUnit, source/package/host hashes, failures and vault provenance.
5. Leave task ledger unchecked unless exact canonical gate and required same-SHA CI pass.

## Mandatory Subsequent Work

This guard is not the positive acceptance implementation. Connect actual exact-byte trusted
reviewer verification, disjoint sealed holdouts with real option media, preregistered
episode/reviewer inference, canonical source/gate and hosted CI revalidation, independent
licensed studies, measured quality/performance and a real 30-day use journal. Add a positive
verified-candidate path only when those contracts are implemented and tested. Preserve the
full protected-worker, durable execution, genuine pipeline, revision, review/export and
owner/editor sustained acceptance scope. No 10/10 claim, spending, model change, licence
acceptance, CI alteration or publication is authorized by this unit.
