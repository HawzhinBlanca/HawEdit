# Adversarial pass #15 — the judge contract

> Run 2026-08-09 on hawapc01 against `2ae692c`.
> Target: **M2.6**, DONE — never attacked. It routes real money and decides which model reads a
> client's Kurdish.

```
CAUGHT  the tier ceiling becomes the 360K with-video figure it exists to refuse
MISSED  the ceiling is exclusive, so a request exactly at 200,000 tokens passes
CAUGHT  an uncounted request is treated as a small one
CAUGHT  a candidate Path A already scored can be re-sent for discovery
CAUGHT  the regression floor drops to one item
CAUGHT  an empty regression set promotes the shadow
CAUGHT  a set below the floor promotes the shadow
MISSED  a tie promotes the shadow
MISSED  more than 20 keyframes are accepted

6/9
```

## The tie test passes for two unrelated reasons

The cell says promotion needs *"a clear win on ≥20 real items, never a tie or an empty set"*. There
is a test called `test_a_shadow_that_merely_ties_is_not_promoted`. It calls

```python
decide_judge(incumbent_wins=5, shadow_wins=5, ties=0)      # total 10
```

which is **below the 20-item floor**, so the floor answers and the tie rule is never consulted:

```
total 10   switch False   "10 items is below the 20-item floor. A win this size is noise…"
total 20   switch False   "gemini-3.1-pro tied with the incumbent and so did not beat it."
```

Its second assertion looks for `"tie"` in any reason — and the header line of *every* decision reads
`regression set: N items — gemini-2.5-pro X, gemini-3.1-pro Y, **ties** Z`. So the word is always
there, whatever was decided.

Two reasons to pass, neither of them the rule. `shadow_wins <= incumbent_wins` → `<` left the suite
green, and a tie above the floor would have promoted the shadow — the switch §3 says to make only
when 3.1 Pro *beats* 2.5 Pro on Hawa's Sorani.

Ten and ten clears the floor. The new test also asserts the floor did **not** answer, so it stays
honest if the floor moves, and a control at eleven against ten promotes — refusing every tie *and*
every win would satisfy the first test and pin the incumbent for ever.

## The ceiling was a boundary nobody stood on

§3: *"Keep each request **under** 200K tokens to stay on the lower Pro price tier."* Exactly 200,000
is not under it. The existing tests assert the constant and refuse requests far over it, so `>=`
could become `>` unnoticed — D-098 and D-122's shape, third time. Pinned at the ceiling, with one
token below as the control so it is a boundary and not a blanket refusal of the with-video mode.

## The keyframe cap

"~20 keyframes" is §3's payload and nothing held the limit. Inline images are billed; D-126 found the
same module's frames could come from anywhere in the media.

The control for it failed first, for a reason that was the code being right: `JudgeRequest` also
refuses frames outside the candidate span, and it checks the count first — so the 21-frame case
raises the count error while a 20-frame request with no span raises the span one. Recorded in the
test.

```
after: 9/9
```

No production code changed. All nine mechanisms were already right; three were unheld.

Gate: `VERIFY OK — 1302 passed, 0 skipped`.
