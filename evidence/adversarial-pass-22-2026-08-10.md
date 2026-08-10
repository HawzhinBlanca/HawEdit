# Adversarial pass #22 — M2.6, the judge contract

> Measured 2026-08-10 on hawapc01 against `7002331`, Python 3.11 in `.venv`.

`PROGRESS.md` M2.6 is **DONE**. `README.md`'s module map says what it is accountable for:

> `judge.py` | §3 Stage 4 | The judge contract: shadow never routed, 200K tier ceiling, promotion
> only on evidence.

Pass #20 listed `judge.py` as a file and never mutated it. This pass reverts each of the three
claims, one mutation at a time, against a baseline verified green first.

## The survivor

```
baseline green: True
...
SURVIVED  VertexGeminiJudge stops resolving itself against §7
...
14/15
```

`VertexGeminiJudge(GeminiJudge)` defines its own `__init__` and does not call `super().__init__`:

```
VertexGeminiJudge defines its own __init__: True
calls super().__init__: False
```

which is right — Vertex authenticates with ADC, and the parent's `__init__` ends by reading
`GEMINI_API_KEY` and refusing without it. The consequence is that `route(self)` is a **copy**, and
the only test of it built the parent class. With the copy deleted:

```
constructed: gemini-3.1-pro
url: https://aiplatform.googleapis.com/v1/projects/proj/locations/global/
     publishers/google/models/gemini-3.1-pro:generateContent
```

Five suites — judge, gemini, path_a, editorial_bench, clip — stayed green while the confidential
ZDR route pointed at the model §3 marks "evaluated, not routed". The guard was correct; its absence
was invisible.

## The fix

`tests/test_gemini.py` names every constructible judge in `_concrete_judges()` and compares that set
**both ways** against `GeminiJudge` and its transitive subclasses. Each named judge is built as the
shadow and must raise `NotRoutable`; the control builds the same constructor with the pinned
incumbent and asserts it reaches the request URL — without it, a constructor that refused
*everything* would pass. Five tests; no production code changed.

## Proof

```
baseline green: True

RED  route() lets the shadow through
RED  to_editorial() lets a shadow verdict become a clip's editorial block
RED  GeminiJudge stops resolving itself against §7 before the first billed call
RED  VertexGeminiJudge stops resolving itself against §7          <- the survivor, now caught
RED  the ceiling becomes exclusive, so a request exactly at 200K ships
RED  an uncounted request is treated as a small one
RED  the real Gemini call stops checking the counted size against the ceiling
RED  Path A discovery stops checking the counted size against the ceiling
RED  video bills at the low-resolution rate while asking for default
RED  cached input is billed at full price
RED  more than §3's 20 keyframes are accepted
RED  the regression-set floor is dropped, so a 3-item win promotes
RED  a tie counts as beating the incumbent
RED  an empty regression set stops being its own refusal
RED  MIN_REGRESSION_ITEMS drops to 1, so one item is a regression set
RED  _is_kurdish accepts anything, so an English title ships
RED  D-076 reverted: the script check runs before §4.1 normalization again
RED  the payoff no longer has to fall inside the clip being cut
RED  the new suite stops naming VertexGeminiJudge, so its §7 check is unheld again

19/19
restored and green: True
```

The last line mutates the new guard rather than the code: removing `VertexGeminiJudge` from the
class list is caught by the bidirectional check, so the list cannot quietly stop describing the
module.

## What held

Both remaining README claims survived every attempt. The 200K ceiling refuses a request at exactly
200,000 tokens and one whose size is unknown, in `judge.py` and again at both real call sites.
Promotion refuses an empty regression set, a set under the 20-item floor, and a tie above it — and
`MIN_REGRESSION_ITEMS` cannot be lowered to 1 without a test failing. Four claims the row does not
make held too: `to_editorial()`'s second refusal of the shadow, `_is_kurdish` on an English title,
D-076's check-after-normalization order, and the payoff-inside-the-clip range.

## Three anchors of mine missed first time

`if total < min_items:`, `if shadow_wins <= incumbent_wins:` and `if total == 0:` were written with
method indentation; `decide_judge` is a module-level function. The audit reported `ANCHOR?(0)` for
each rather than counting them, which is why it counts occurrences instead of substituting blindly —
a mutation that does not apply must never read as a survivor or as a catch.

Gate: `VERIFY OK — hawedit gate green`, 1427 tests (floor 1422 → 1427).
