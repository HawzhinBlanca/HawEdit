# Paired Review Data Without Fabricated Authority

2026-10-03. Approved-by: Wareen, parent explicit seven-phase implementation request,
BLUEPRINT §§2, 8.2-8.3 and D-276's evidence-backed evaluation/authentication contract.
Approval covers code/preparation, not paid/human studies, methodology preregistration,
spending, licences, reviewer trust configuration, publication or release.
Baseline HEAD 372a16645d7a8558bc6cedcff34a9fbfa13f712f, uncommitted package
6bde42cba644a4510bbdb1bdd28596dba7cece5c328612c6dcbcb0e3d7f0b2cb.

## Research

statistical-acceptance-research.md preserves actual order-dependence, duplicate-reviewer,
public-seed leakage, unverified scorecard admission and preference-to-QC counterexamples.
Fresh comparison_repair_serena.py captures current definitions/callers before source edits.
Current PairRating has one overall hook/clarity/shareability score, one overall misleading
flag and a preference. It cannot identify either option's score or misleading status.
analyze_study infers differences from cumulative wins, pools repeated observations as
independent trials and authorizes superiority from a pooled Wilson interval. validate_ratings
coerces misleading text/integers to bool and indexes absent fields without contextual refusal.
Direct dataclass constructors do not enforce complete/distinct reviewer-pair observations.
export_to_qc_records invents 60 watched seconds and pass approval from preference. QcRecord
requires positive watched time, so inventing zero/review records is not an acceptable fix.

## Implementation

Extend the existing kit with a version-2 per-option rating object and a paired constructor.
Each option records its own bounded integer scores and explicit misleading flag; optional
viewing/correction observations remain unknown unless supplied. Legacy version-1 input
remains parseable but cannot acquire unrecoverable option differences or fidelity attribution.
Version-2 payloads and generated Sorani forms use separate A/B values; serialization records
the version and preserves values. Strictly reject booleans-as-scores, missing/extra fields,
coerced flags, malformed timestamps, mixed schemas and duplicate reviewer/pair observations.
Reviewer strings are self-declared labels, not authenticated identity; never infer independence
or trusted signing authority from their count.

Compute descriptive preference counts and A/B-mapped paired differences/flag rates exactly,
independent of iteration order. Unknown legacy differences/flag attribution are null, never
invented zero or winner-associated scores. Preserve tie accounting and nominal reviewer/pair
counts. Separate a clearly labelled pooled independent-Bernoulli Wilson reference from the
currently unavailable episode/repeated-reviewer inference; ci_lower/ci_upper remain unknown
and better_than_a_team remains unapproved until a verified preregistered study analysis
supplies the required evidence. This unit does not choose a new cluster/reviewer method.
The reference formula is a supporting binomial-proportion interval, not a model of
episode/reviewer dependence: https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm.
NormalDist.inv_cdf is the standard-library inverse normal CDF:
https://docs.python.org/3/library/statistics.html#statistics.NormalDist.inv_cdf.
Correct the shared Wilson helper's unsupported-confidence behavior with stdlib NormalDist,
preserving its 95% results and visual_scorecard caller. The reference is not a release verdict.

The old QC export refuses explicitly: comparative preference is not fidelity QC, signature
authentication, observed watched time or exact-byte publication approval. Retain the public
function/signature for contextual migration, never fabricate records. Actual signed fidelity
review stays in the existing QC/acceptance machinery and approved review/delivery units.
Keep old tests' score/count/refusal assertions; replace only the prior false-authority
expectations with stronger explicit nonauthorization assertions and new paired evidence.

No blinding, scorecard authorization, signed study/holdout, model or pipeline source is
silently deemed fixed. Those are mandatory next units, not reduced acceptance requirements.
No dependency, protected harness/golden/fixture or frozen BLUEPRINT edit is required.
Freeze tested README/PROGRESS/ADR mappings before full canonical collection. Test-first,
complete affected groups, exact verify.sh, actual source/runtime/hardware and terminal XML.
No row flip without green gate and same committed-SHA required CI.

## Caller Impact

PairRating/RaterSubmission are used by validate_ratings, analyze_study, QC export and the
comparison tests. Forms/Markdown are called by their existing Sorani-form test and public
exports; retain rubric labels while explicitly requiring A/B scoring. StudyMetrics has no
production caller outside this kit; existing tests read counts, rates, confidence and the
authority flag. Wilson is also used by compute_visual_scorecard; preserve valid95 results
and run that full module. Source-stage/QC/reconciliation signatures are unchanged. Standalone
historical counterexamples are diagnostic callers; preserve their old artifacts rather than
rewriting them. Imports/file-symbol fallbacks remain explicit in fresh Serena evidence.

## EARS / Named Regressions

- PC1: WHEN A/B ratings are supplied, THE kit SHALL retain each option's scores/flags and
  compute correct order-invariant system-minus-human descriptive differences.
  Tests: test_comparison_paired_differences_are_order_invariant,
  test_comparison_paired_flags_follow_option_not_preference,
  test_comparison_paired_submission_roundtrip.
- PC2: WHEN old overall ratings are analyzed, THE kit SHALL report unknown option-specific
  differences/flags rather than infer them from preference.
  Test: test_comparison_legacy_differences_are_unknown.
- PC3: WHEN reviewer/pair observations repeat or maps/payloads are malformed, THE kit
  SHALL refuse contextual invalid evidence without fabricating sample size or values.
  Tests: test_comparison_duplicate_observations_refused,
  test_comparison_malformed_payloads_are_contextual,
  test_comparison_unblinding_map_is_complete_and_bijective.
- PC4: WHEN only descriptive votes/labels exist, THE kit SHALL separate independent
  reference intervals from unavailable clustered inference and SHALL NOT authorize superiority.
  Test: test_comparison_repeated_ratings_do_not_authorize_superiority.
- PC5: WHEN a supported confidence is requested, THE Wilson helper SHALL use that actual
  confidence and reject invalid sample/proportion/confidence values.
  Test: test_comparison_wilson_uses_requested_confidence.
- PC6: WHEN comparative preferences are exported as QC, THE kit SHALL refuse without
  producing approval or invented watched time.
  Test: test_comparison_preference_cannot_become_qc_approval.
- PC7: WHEN a new review form is generated, THE kit SHALL require explicit A/B data and
  identify the version rather than imply one overall score is a paired measurement.
  Test: test_comparison_form_requires_each_option.

These contracts are not authenticated/repeated-reviewer inference, sealed blinding,
scorecard/release authorization, commissioned evaluation or completed T8.
