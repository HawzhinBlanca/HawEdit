# The aligner's infeasibility refusal could be deleted whole, with 1,099 tests still green

> Measured 2026-08-09 on hawapc01 against `f9a88df`.

M1.1 is DONE and its row claims *"Monotone non-overlapping spans, every token framed, infeasible
input refused rather than guessed."* The 2026-08-09 adversarial pass reported five unprotected
guards in `forced_alignment.py`. Re-measured here rather than taken on trust — the count is right
and the framing is wrong, and the difference matters.

## Every guard in the module, audited in two phases

Phase 1 runs each mutation against the files M1.1 cites; anything caught there is definitively
protected. Phase 2 re-runs the survivors against the **whole** suite, which is the only thing that
separates "genuinely unprotected" from "caught somewhere the row does not mention". Both baselines
verified green first.

```
baseline targeted: GREEN
baseline full    : GREEN

CAUGHT    empty emissions refused
CAUGHT    empty tokens refused
CAUGHT    ragged emissions matrix refused
CAUGHT    blank_id outside the vocabulary refused
CAUGHT    token id outside the vocabulary refused
survived targeted -> checking full suite: too few frames for the token sequence refused
survived targeted -> checking full suite: an unreachable end state refused
survived targeted -> checking full suite: a dead end during backtracking refused
survived targeted -> checking full suite: every token must get a frame
survived targeted -> checking full suite: frame_duration_ms must be positive
survived targeted -> checking full suite: a word with no tokens refused

CAUGHT ELSEWHERE   too few frames for the token sequence refused
UNPROTECTED        an unreachable end state refused
UNPROTECTED        a dead end during backtracking refused
UNPROTECTED        every token must get a frame
UNPROTECTED        frame_duration_ms must be positive
UNPROTECTED        a word with no tokens refused
```

Five unprotected, matching the pass's count exactly.

## Three of them are one refusal, not three gaps

Removing any single member of the trio — the unreachable-end-state check, the backtracking
dead-end check, the every-token-framed check — leaves the refusal intact, because the next one
catches the same condition:

```
=== unmutated ===                      === end_state_unreachable REMOVED ===
  token -inf everywhere   Infeasible     token -inf everywhere   Infeasible
  everything -inf         Infeasible     everything -inf         Infeasible
=== backtrack_dead_end REMOVED ===     === every_token_framed REMOVED ===
  token -inf everywhere   Infeasible     token -inf everywhere   Infeasible
  everything -inf         Infeasible     everything -inf         Infeasible
```

Traced, the unmutated path raises at line 186 — the end-state check — and with that gone the
backtracking check picks it up. So they are **mutually redundant by construction**, and a
single-guard mutation surviving is the expected result rather than a hole. Reporting them as three
separate unprotected guards overstates the finding threefold.

## What was actually unprotected, and it is worse than the count suggested

Delete all three together:

```
$ python -c "viterbi_align([[0.0, -inf, -inf] * 10], [1], blank_id=0)"
KeyError: 0

$ pytest tests/ -q          ->  exit=0, 0 FAILED
```

**The full suite passes with the entire infeasibility chain removed**, while the function degrades
from a documented `AlignmentInfeasible` — whose message explains that aligning anyway "would
invent timings, and a wrong word boundary becomes a clip that starts mid-word with nothing
downstream able to detect it" — to a bare `KeyError: 0` out of the span-assembly loop. No caller
could interpret that, and §4.2's spans feed §5's sentence anchors and every caption time.

So the real finding is one unprotected refusal implemented three redundant ways, plus two
genuinely separate untested refusals (`frame_duration_ms <= 0`, and a word carrying no tokens).
All three are reachable through the public API — verified before writing a line of test, because a
contrived test for an unreachable defensive check is theatre:

```
frame_duration_ms = 0     ValueError: frame_duration_ms must be positive
frame_duration_ms = -5    ValueError: frame_duration_ms must be positive
word with no tokens       ValueError: word 'a' has no tokens...
all -inf for the token    AlignmentInfeasible: 10 frames cannot emit 1 tokens...
```

## Tests added, with controls

Five tests: the infeasible-emissions refusal (three input shapes), the non-positive frame
duration (`0`, `-5`, `-0.001`), and the no-tokens word (alone and as one word among several, so
the refusal is not order-dependent).

Two controls, because a refusal test passes for a function that rejects everything it is handed:
`test_a_feasible_alignment_is_still_produced` aligns the same shape of input with the token
reachable, and `test_a_positive_frame_duration_still_times_words` requires two words to come back
with non-overlapping times.

The infeasible test asserts the **documented exception type and message**, not merely that
something raised — that is the whole distinction between the refusal and the `KeyError` the
deletion produces.

## Re-audit after the tests

Same audit, after:

```
CAUGHT    frame_duration_ms must be positive
CAUGHT    a word with no tokens refused

CAUGHT ELSEWHERE   too few frames for the token sequence refused
UNPROTECTED        an unreachable end state refused
UNPROTECTED        a dead end during backtracking refused
UNPROTECTED        every token must get a frame

7/11 caught by the targeted files      (was 5/11)
```

The two standalone refusals are now protected. The trio is still individually revertible, **which
is the correct outcome and was the point of measuring redundancy first**: each link is covered by
the others, so no single-link mutation can be observed, and a test contrived to make one
observable would be testing the implementation rather than the contract.

What is now protected is the thing that was actually broken — the chain as a whole:

```
whole chain removed, before this change:  pytest exit=0, 0 FAILED
whole chain removed, after  this change:  pytest exit=1, 1 FAILED
  FAILED tests/test_forced_alignment.py::test_emissions_that_cannot_emit_the_tokens_are_refused_not_guessed
```

## What this says about the "26 unprotected guards" figure

That number came out of the adversarial pass and I repeated it across three iterations. For this
module the count was exact and the framing inflated it threefold: five reported, three of which are
one refusal. The lesson generalises to the other 21 — a guard that survives its own mutation
because a sibling catches the same condition is redundancy, not exposure, and only removing the
whole set distinguishes them. Each remaining module needs that same two-step treatment rather than
the headline count.

Gate: `VERIFY OK — 1104 passed, 0 skipped`.
