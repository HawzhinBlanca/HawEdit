# Adversarial pass #10 — the escalation rule

> Run 2026-08-09 on hawapc01 against `bba56a9`.
> Target: **M1.5**, DONE — §3 Stage 1's escalation rule, never attacked.

Fifteen DONE rows in the ledger have never had a pass run at them. M1.5 is the shortest cell of the
fifteen — 252 characters — on one of the few rules §3 states as an algorithm rather than an
intention:

> "compute mean token log-probability per segment from CTC posteriors. Route the bottom quartile,
> and any segment where LLM-7B and CTC-3B disagree materially, to the validator. Never escalate on
> duration or word-count heuristics."

## What survived

The row's claims, checked against the code rather than re-read:

```
"§3's prohibition asserted directly"   two tests, and both mutations are CAUGHT
"Threshold: D-015"                     D-015 records 0.15; the constant is 0.15
"duration_s ... no code path reads it"  grep: one declaration, zero reads
```

And eight of eleven mechanisms are held by the suite:

```
CAUGHT  half the batch escalated instead of the bottom quartile
CAUGHT  the TOP quartile by confidence escalated
CAUGHT  escalation needing BOTH signals instead of either
CAUGHT  duration escalates a segment (§3's prohibition)
CAUGHT  word count escalates a segment (§3's prohibition)
CAUGHT  disagreement measured on raw text, not normalized
CAUGHT  a positive mean_logprob accepted
CAUGHT  the disagreement signal never consulted
```

## What did not — all three in `materially_disagree`

**The reference and the hypothesis were interchangeable.** Normalized CER divides by the reference
length, so it is asymmetric; §3 makes LLM-7B canonical, so the LLM is the reference. Swapping the
arguments left the suite green. Measured on a pair that straddles the threshold one way only:

```
llm "ڕۆژنامەوانی کور"  15 normalized chars
ctc "ڕۆژنامەوانی ک"    13
  cer(llm, ctc) = 0.1333   agreement      (as written)
  cer(ctc, llm) = 0.1538   disagreement   (swapped)
```

The first two pairs tried escalated either way — 0.5926 against 1.4545, and 4.0 against 0.8 — so a
test built on them would have passed for both argument orders. Finding a straddling pair is what
makes the test discriminate, and it is why the fixture is a length relationship rather than a
sentence.

**The boundary was unpinned.** `>=` became `>` for free. Every existing test passes
`DEFAULT_DISAGREEMENT_CER` or a value nowhere near it, so the operator could move without anything
noticing — the same shape as D-098, where every §4.2 pause test took the constant and changing
500 to 800 left 1,170 tests green. Pinned now at a measured pair: 20 normalized characters, three
edits, **cer exactly 0.15**.

**A silent model read as agreement.** The module's own words: one model producing nothing "is the
strongest disagreement available". Returning `False` there was free, and it is precisely the case
the validator is for — CTC yielding nothing where the LLM heard speech. Pinned both ways, with a
control that *both* silent is agreement, because returning `True` whenever either side is empty
satisfies the positive assertions and routes every silent segment to a 4 GiB model. A fourth test
drives it through `select_for_validation`: the predicate being right is not the decision acting on
it, which is the fourth-time-lucky lesson of D-105, D-108, D-112 and D-118.

```
after the fix

11/11
```

## What the pass deliberately did not do

M1.5 stays **DONE**. Its Definition of Done is the rule; the rule is complete, faithful to §3, and
now fully pinned. That nothing calls it is true and recorded — `select_for_validation` has no caller
in `src/` because `ctc_text` is never computed — but that is M1.4's named shortfall, and duplicating
it here would make the tally disagree with itself. The cell now states it rather than leaving a
reader to find it under another row.

Gate: `VERIFY OK — 1281 passed, 0 skipped`.
