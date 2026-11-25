# Candidate framing parity plan

Approved-by: Wareen, 2026-10-04, "fix all and do rel test again" (camera repair and real ZAR38 retest; no cloud cap, model/licence change or publication inferred)

Baseline: `7fa7d3a37efb8f11d68ecc2b9a52ecd082f7535e`, 2026-10-04.
Owner approval above authorizes this scoped implementation under AGENTS.md.
This is the next quality implementation unit, not completion
of the original 10/10 program or a substitute for ASR repair.

## One sequential implementation unit

1. Add test-first named CF-1 through CF-7 regressions that exercise both actual
   pipeline routes. Retain the pre-fix ignored-tracker diagnostic; no golden,
   fixture, failed evidence or existing assertion rewrite to fit the defect.
2. Extract the camera decision shared by single and episode rendering, with a
   typed result carrying crop mode, focus points, split crops, face geometry
   and validated turns. Reuse existing association and layout functions. Preserve
   public signatures and source-change checks. Do not copy the single path's
   potential split-overwrite behavior into the shared implementation.
3. Apply exact requested split mode and production refusal policy in both routes;
   no face/centre substitution after requested association refusal. Persist the
   real resolved configuration and validated turns in the edit plan. Keep
   per-candidate refusal and review-only artifact semantics.
4. Record the explicit empty-association production refusal in DECISIONS.md as an
   ADR extension after approval, because the current single-path docstring allows
   an empty-result face-only substitution. Reconcile that statement visibly with
   the owner's all-stop policy; do not silently rewrite historical claims.
5. Run every affected caller module, real decoded framing checks, then exact
   `bash scripts/verify.sh`. Respect the current VEX failure; never rebind or
   extend its expiry to make the gate pass. Ledger promotion requires its
   prescribed script and applicable same-SHA CI. Local commit only if reviewed;
   nothing pushed or published.

## Quality work following this unit

ZAR38 still requires native reference for its failing ASR spans and measured
development diagnosis under the champion policy. A successful ASR repair cannot
be asserted by omitting gaps, guessing words or changing the decoder silently.

After target video identification, freeze that output's hashes and evaluate a
source-linked revision for: complete hook/payoff/caveats; correct speaker views;
headline/caption/source-graphic non-overlap; readable RTL at actual playback;
natural pauses and faithful chronology; decoded output vs edit-plan timing.
Keep rejected revisions and correction time. Use a separate scoped map/spec
before touching those behaviors. Do not wire speculative story/critic modules
merely because their names imply editorial intelligence.

No new model, dependency, licence acceptance, cloud spending, trust identity,
release authority or acceptance threshold change is included. No cloud budget
has been inferred from earlier generic approval. The independent study split
repair remains separately pending; synthetic ratings do not establish its quality.
