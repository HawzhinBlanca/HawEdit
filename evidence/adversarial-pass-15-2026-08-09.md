# Adversarial pass #15 - the judge contract

Run 2026-08-09 against upstream `2ae692c`; semantically integrated into the readiness branch as
D-158 because D-128 was already assigned there.

The pass attacked nine Stage 4 mechanisms. Six already had discriminating coverage: the 200K
ceiling against the with-video estimate, refusal of uncounted requests, refusal to pay twice for a
Path A candidate, the 20-item regression floor, and refusal of empty and below-floor regression
sets. Three production behaviors were correct but insufficiently held.

## Tie promotion

The prior tie test called `decide_judge(5, 5)`. Its ten items are below the 20-item floor, so that
branch answered before the tie rule. Its reason assertion searched for `tie`, which also matched
the `ties 0` summary printed for every decision. The replacement uses 10 against 10, proves the
floor did not answer, and adds an 11-against-10 control that must promote.

## Token ceiling

Section 3 says each request stays *under* 200K tokens. The new boundary test refuses exactly
200,000 and accepts 199,999, preventing `>=` from silently becoming `>` or a blanket refusal.

## Keyframe ceiling

Inline keyframes are billed payload. The new test refuses 21 frames and accepts exactly 20 whose
timestamps lie within the candidate span, separately holding both the count and provenance rules.

No production code changed. The value of this pass is that all nine mechanisms are now guarded by
tests that fail for the targeted mutation and include the opposite-direction control.
