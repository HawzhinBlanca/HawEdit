# Impact map — candidate spans

## `_PROMPT` — `path_a.py:80` — **gains the duration range**

| caller | site | covered by |
|---|---|---|
| `PathADiscovery.discover` | `path_a.py` | `tests/test_path_a.py` prompt tests |

The prompt is asserted on in tests today; a new required sentence must be asserted too, or it
can be dropped without a red suite.

## `_complete_sentences_within` — `pipeline.py:932` — **unchanged**

Deliberately shared with `_rejected_candidates` (its own docstring says why). Growth happens
*around* a seed rather than by loosening this predicate, so the shared meaning stays intact.

| caller | site | covered by |
|---|---|---|
| `_sentence_run_for_candidate` | `pipeline.py` | `test_the_selector_returns_a_run_for_one_candidate` |
| `_rejected_candidates` | `pipeline.py` | `tests/test_pipeline.py` rejection suite |

## `_sentence_run_for_candidate` — `pipeline.py` — **gains growth**

| caller | site | covered by |
|---|---|---|
| `_automatic_sentence_selection` | `pipeline.py` | `test_auto_selection_still_picks_what_it_picked_before` |
| `_judgeable_plans` | `pipeline.py` | `test_an_ineligible_candidate_costs_no_billed_call` |

Both existing tests pin current behaviour and both must keep passing at the default range, or
the change is not additive.

## `_judgeable_plans` — `pipeline.py` — **eligibility widens**

Today: a candidate is eligible only if a complete sentence lies wholly inside it. After: a
candidate is eligible if a run can be *grown* around it. Measured effect to verify: ep01 went
1/15 eligible and ep10 5/18.

## Gap found

No test asserts anything about candidate *duration* — not a minimum, a maximum, or a
distribution. Fifteen candidates at 1.1–22.9 s passed every check in the suite. That is why the
fragments reached a billed judge.
