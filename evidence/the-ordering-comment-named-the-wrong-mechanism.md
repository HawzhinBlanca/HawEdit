# §4.1's call order was right, and the reason recorded for it was not the operative one

`normalize_sorani` normalizes first and separates second, with a comment saying why:

> Order matters: the encoding fixes must land before any dictionary lookup, or separation would
> fail on exactly the text §4.1 exists for — a word typed with `ه`+ZWNJ is not the dictionary's
> spelling of it, so it would never be recognised and never be separated.

## How this iteration went wrong first, and how that was caught

A mutation sweep over `normalize.py` returned **4/6**, with the reversal apparently SURVIVING.
That was **my own bad mutation**: it rewrote the first line to `normalize(separate(text))` and
left the trailing `return separate_conjunctive_waw(normalized)` in place, so it *added* a pass
rather than reordering. The property was held all along, by
`test_normalization_runs_the_encoding_fixes_before_the_lexicon_lookup`, which the corrected
mutation reddens.

A control written on that false premise was then measured and found **vacuous** — it wrapped the
comparison in `normalize()`, which re-joins the space, so it passed for the mutated code and the
shipped code alike. It was removed rather than kept. *"A test that passes for both measures
nothing"* applies to tests written in this loop as much as to the ones it audits.

## What the chase did find: the recorded mechanism is not the operative one

```
  ZWNJ text                : 'وکتێبه‌کان'
  what \w+ tokenises it to : ['وکتێبه', 'کان']
  after normalization      : 'وکتێبەکان'
  tokenises to             : ['وکتێبەکان']

  is_sorani_word('کتێبه')     : False      <- the fragment
  is_sorani_word('کتێبەکان') : True       <- the whole word
```

ZWNJ is **U+200C, a format character**, so `_TOKEN`'s `\w+` does not match it and a
ZWNJ-typed word arrives as **two tokens**. The lookup never receives the word to fail on. The
old comment describes a real effect — the spellings do differ — but names a cause that is not
the one operating, and the difference is not academic:

**Reading the old comment, the natural repair is to normalize the remainder inside the lookup.**
Measured, that repair changes nothing: `separate_conjunctive_waw` still returns the ZWNJ input
untouched, because the token was already broken in half before the lookup was reached. Someone
would have made that change, seen no test fail, and believed the order was no longer load-bearing.

## What the order is worth

Across KLPT's dictionary, with each word rendered as an Arabic keyboard emits it:

```
dictionary entries: 24,894
candidates (contain ە, recognised, و+word is not a word): 11,896

checked                        : 400
separated by the shipped order : 400
separated by the reversed order: 3

example
  dictionary word  : ئابخانە
  joined, as typed : 'وئابخانه‌'
  shipped order    : 'و ئابخانە'   <- separated
  reversed order   : 'وئابخانە'   <- still joined
```

Not an edge case: §4.1's fourth collision working or not working on exactly the text §4.1 exists
for, with `transcript.raw.json` untouched either way and every index, embedding and model input
reading the joined form (Kurdish invariant #3).

## Mutation audit — 2/3 lint-clean, and the survivor is the point

```
CAUGHT    the token pattern absorbs ZWNJ — the repair the OLD comment invites
            <- ONLY tests/test_waw.py::test_zwnj_fragments_the_token_which_is_why_the_order_is_what_it_is
CAUGHT    the token pattern stops being word-aware entirely
            tests/test_waw.py::test_punctuation_is_preserved_around_a_split
            tests/test_waw.py::test_zwnj_fragments_the_token_…
SURVIVED  the lookup normalises its own remainder — the other repair the old comment invites

files restored byte-identical: True
2/3 caught lint-clean
```

**The first mutation is caught by the new test and by nothing else**, which is what earns it a
place beside a property that was already held.

**The survivor is a demonstrated no-op and is not counted.** Normalising the remainder inside
the lookup changes no output, for the structural reason the corrected comment now gives — the
token is already fragmented. It survives because there is nothing to catch, the same shape as
D-170's blank-skip clause. Its survival *confirms* the corrected mechanism rather than exposing a
gap.

## What changed

The comment in `normalize.py` now states the measured mechanism and its numbers. No behaviour
changed: the call order was correct before and is correct now. What is different is that the
reason a future reader acts on is the true one, and the tokenization it rests on is pinned.
