# Adversarial pass 27 — M0.2, and the column §7 has that nothing read

M0.2's guarantee is that the model registry **is** §7 rather than a copy of it that drifts,
enforced by parsing the frozen `BLUEPRINT.md` and requiring exact set correspondence. §7's
table has three columns:

    | Component | Model | Licence |

`tests/test_registry.py` parses `r[1]`. Nothing anywhere read `r[2]`.

That matters because the second rule this module enforces is *NonCommercial is a hard reject*,
and `assert_commercially_usable` "keys off the licence, not off those two names" — so the
recorded licence is the datum the whole policy rests on.

## The premise was checked first, and the data is right

Every registered entry against §7's own Licence column:

```
§7 Model cell                                    §7 Licence                                   code
PySceneDetect                                    open                                         open (§7, not independently verified)
Silero VAD                                       MIT                                          MIT
pyannote/speaker-diarization-community-1         CC-BY-4.0 (attribution required, gated repo) CC-BY-4.0
omniASR_LLM_7B_v2                                Apache 2.0                                   Apache-2.0
omniASR_CTC_3B_v2                                Apache 2.0                                   Apache-2.0
rzgar/qwen3-asr-sorani-kurdish-ckb-v1            Apache 2.0                                   Apache-2.0
Custom Viterbi on CTC emissions                  in-house                                     in-house
KLPT                                             open                                         CC-BY-SA-4.0
Qwen3-VL-Embedding-2B                            Apache 2.0                                   Apache-2.0
Qwen3-VL-Reranker-2B                             Apache 2.0                                   Apache-2.0
MCG-NJU/VideoChat3-4B                            Apache 2.0                                   Apache-2.0
MCG-NJU/TimeLens2-4B                             Apache 2.0                                   Apache-2.0
gemini-2.5-pro, pinned                           commercial                                   commercial
gemini-3.1-pro                                   commercial                                   commercial
ASS + libass/HarfBuzz/FriBidi                    LGPL/GPL                                     LGPL/GPL
```

15 §7 rows, 15 code entries, and the only two that differ are the two the module docstring
already accounts for: PySceneDetect restates §7's "open" more precisely, and KLPT is D-002's
narrowing read out of the shipped wheel metadata. **No live mismatch — the claim is true.**

It is also held by nothing, which is what the pass is for.

## What survived: 1/4

Four licences changed one at a time in `registry.py`, whole suite each time, against a baseline
verified green first:

```
baseline:
  lint clean: True   pytest exit: 0   failures: []

SURVIVED  omniASR_CTC_3B_v2: Apache-2.0 -> MIT (§7 says Apache 2.0)
SURVIVED  KLPT: CC-BY-SA-4.0 -> CC-BY-4.0 (drops share-alike from the shipped notice)
SURVIVED  Community-1: CC-BY-4.0 -> CC-BY-SA-4.0 (invents a share-alike obligation)
CAUGHT    captions: LGPL/GPL -> Apache-2.0 (drops the notice entirely)
            tests/test_claims.py::test_every_readme_attribution_bullet_is_generated

1/4 caught
```

The one that was caught was caught for a reason that has nothing to do with licences:
Apache-2.0 requires no attribution, so the libass **subject** vanished from the generated list
and the README's both-directions bookkeeping noticed a missing bullet. Change a licence to
another that keeps the same attribution flag and nothing sees it at all.

Two of the survivors alter what shipped product documentation *says about someone else's
licence*: KLPT's share-alike obligation disappears, and Community-1 gains one CC-BY-4.0 does
not impose.

## And the same hole from the other side

The README's Attribution section is the mitigation §10 names for this exact risk, and the
section itself says the test asserts it "in both directions". It compares **subjects** — the
part of each notice before the em dash. So the bullet was edited to read:

    - KLPT — Sina Ahmadi, MIT, no attribution required.

against a generator emitting `CC-BY-SA-4.0`, and:

```
tests/test_claims.py tests/test_registry.py  ->  73 passed
```

Shipped documentation making a false statement about a third party's licence, with the suite
green. The share-alike clause lives on the bullet's *second* line, which the line-by-line read
never looked at either.

## The fix

One root: the licence is stated in three places — `BLUEPRINT.md` §7, `registry.py`, and the
README — and only the model **names** were ever cross-checked.

* `test_every_registered_licence_is_the_one_section_7_states` compares each entry to §7's
  Licence column. §7 and the code state the same licence at different widths in both
  directions (`CC-BY-4.0` vs `CC-BY-4.0 (attribution required, gated repo)`; `open` vs
  `open (§7, not independently verified)`), so the rule is that one's words must be a
  **contiguous run** of the other's. `CC-BY-SA-4.0` is not a run of `CC-BY-4.0 …`.
* `LICENCE_DIVERGENCES` in `registry.py` carries the recorded restatements — today only KLPT —
  **pinned by value**, so an exemption cannot become a licence-shaped hole.
* `test_every_recorded_divergence_actually_diverges` is the control: a listed entry that agrees
  with §7 is a stale exemption, and the reason must cite a `D-0NN`.
* `test_every_noncommercial_exclusion_is_noncommercial_in_code` binds §7's two CC-BY-NC-4.0
  exclusion reasons to the code, both ways.
* `test_the_readme_states_the_same_licence_the_notice_does` and its reverse close the README
  side, reading whole bullets so continuation lines are visible.

## A first spelling that was wrong, and how it failed

The NC test first asserted on `commercial_use` rather than on the licence name. It failed on
`CLIP as primary retrieval`: the other seven exclusions are `NOT_ASSESSED`, which is
`commercial_use=False` **by design** — default-deny, "we have not cleared them", which the
module docstring is explicit is *not* the same claim as NonCommercial. Asserting on the flag
would have flattened that distinction into the code. Keyed on the name instead.

## Mutation audit — 8/8, lint-clean, against a baseline verified green first

The four survivors above, plus a paired control for each new guard: a control is mutated
together with the state it describes, never alone (D-162). Whole suite per mutation.

```
baseline:
  lint clean: True   pytest exit: 0   failures: []

CAUGHT    survivor 1: omniASR_CTC_3B_v2 Apache-2.0 -> MIT (§7 says Apache 2.0)
            test_every_registered_licence_is_the_one_section_7_states
CAUGHT    survivor 2: KLPT CC-BY-SA-4.0 -> CC-BY-4.0 (drops share-alike from shipped docs)
            test_no_readme_attribution_bullet_claims_an_obligation_the_registry_does_not
            test_the_readme_states_the_same_licence_the_notice_does
            test_every_recorded_divergence_actually_diverges
CAUGHT    survivor 3: Community-1 CC-BY-4.0 -> CC-BY-SA-4.0 (invents a share-alike obligation)
            test_the_readme_states_the_same_licence_the_notice_does
            test_every_registered_licence_is_the_one_section_7_states
CAUGHT    survivor 4: the README bullet states a licence KLPT does not have
            test_the_readme_states_the_same_licence_the_notice_does
CAUGHT    control: KLPT's exemption removed while its licence still diverges from §7
            test_every_registered_licence_is_the_one_section_7_states
CAUGHT    control: an exemption for an entry that agrees with §7 (a stale row)
            test_every_recorded_divergence_actually_diverges
CAUGHT    control: the README drops the share-alike the registry records for KLPT
            test_the_readme_states_the_same_licence_the_notice_does
CAUGHT    control: the README claims share-alike for a licence that imposes none
            test_no_readme_attribution_bullet_claims_an_obligation_the_registry_does_not

files restored byte-identical: True
8/8 caught lint-clean
```

Survivor 2 is caught three ways, including by the divergence table's **pinned value** — the
exemption cannot become a hole. The two exemption controls are the pair that matters: removing
KLPT's row while its licence still diverges reddens the §7 check, and adding a row for an entry
that agrees with §7 reddens the staleness check, so the table is load-bearing in both
directions rather than a list nobody reads.

## The baseline check earned its keep again

The first run of this audit reported `BASELINE NOT GREEN` — `RUF022`, my own new `__all__`
entry out of order, which reddened the three gate-as-subprocess tests in `test_gate.py`. Without
that check, eight mutations would have reported CAUGHT on a tree that was already red, and every
one of those catches would have been ruff. Fixed and re-run from a verified-green baseline.

## Gate

`VERIFY OK — hawedit gate green`, 1552 passed, 0 skipped. Floor 1547 → 1552.
No production behaviour changed: one new data table and five new tests.
