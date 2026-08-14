# §4.1 conjunctive `و` separation — measured on KLPT's Sorani dictionary

**Date:** 2026-08-07 · **Task:** M1.7 · **Decision:** D-026 · **Supersedes the gap in:** D-003

§4.1 lists five encoding/orthography collisions. KLPT's `normalize()` covers four (D-003).
The fifth — the conjunction `و` typed onto the preceding word — it does not, and §4.1 only
says "AsoSoft applies a separation algorithm" without giving one.

## The rule

    split `و` + R  →  `و` R    only if   R is a valid Sorani word   AND   `و`+R is not.

Validity is `klpt.stem.Stem.check_spelling`, which is morphology-aware: `کتێبەکان` (the
inflected plural "the books") validates, so the rule fires on real running text and not only
on the ~24k citation forms.

The rule is a refusal, not a prediction. Where the evidence is ambiguous it declines. The bias
is one-directional and chosen deliberately: **under-split, never mis-split.** A joined `و` left
alone costs recall in the §2 index, and character 3-grams absorb part of that. A real word torn
in half costs correctness in `transcript.norm.json` — which every index, embedding and model
input reads under Kurdish invariant #3 — and nothing absorbs that.

## Measurements

Run over every headword in `klpt/data/ckb-Arab.dic`, after §4.1 normalization.

```json
{
  "lexicon_entries": 24894,
  "dictionary_words_damaged": 0,
  "waw_initial_words": 504,
  "unsplittable_waw_initial_words": 19,
  "unsplittable_examples": [
    "وتار", "وترێ", "وتوو", "وتووچی", "وسمە", "وشکێنی", "وشیار", "وشە", "ولێرە",
    "وچان", "وڕمان", "وڕک", "وڕێڵە", "وڕە", "وی", "ویست", "ویلەر", "ویکۆڵ", "وێ"
  ],
  "constructible_joined_forms": 24390,
  "joined_forms_recovered": 24124,
  "joined_forms_not_recovered": 266,
  "recall_pct": 98.91
}
```

### Safety: 0 of 24,894

No word in the dictionary is split by this rule. This is the load-bearing claim and it is
checked exhaustively, not by example, in `tests/test_waw.py::test_no_dictionary_word_is_ever_split`.

### The 19 unsplittable words

These start with `و` **and are words in their own right**, so the second condition blocks them
permanently — `وتار` ("article"), `وشە` ("word"), `ویست` ("will"). When one of them appears as
`و` + a noun the conjunction stays joined and the index keeps the joined form. That is the
price of never producing "and tar" from "article", and it is a price worth paying: 19 words
under-separated against a guarantee that no word is ever destroyed.

`ولێرە` is the interesting one — plausibly `و` + `لێرە` ("and here") far more often than
whatever headword put it in the dictionary. The rule still declines. Resolving it needs
context, not a lexicon, and context-sensitive normalization of the canonical artifact is a
much larger claim than this task is making.

### Recall: 98.91%, and the 1.09% has one cause

Of the 24,390 constructible joined forms (`و` + each non-`و`-initial headword), 266 do not
separate back. Every one of them contains a bare medial `ه` (U+0647) or `ھ` (U+06BE) —
`بهار`, `بهەشت`, `ئارهات`, `ئەھ`. KLPT's spell checker rejects these headwords from its own
dictionary, so the remainder never validates and the rule correctly declines to act on
evidence it does not have.

This is the same gap D-013 recorded from the other direction: §4.1's collision table lists
`ه`+ZWNJ → `ە` but says nothing about bare medial `ه` or about `ھ` U+06BE, and KLPT's
`normalize()` leaves both alone. The two findings agree, which is worth something — the
recall ceiling here is not a property of the separation rule, it is the §4.1 gap D-013 found,
observed through a second instrument.

## What this does not establish

Nothing about running Kurdish speech. The dictionary is a word list; the incidence of joined
`و` in real Sorani transcripts, and the recall the §2 index actually gains, need the labelled
corpus (`BLOCKED.md` #1, #6). What is established is that turning this on cannot damage a
known word, and that is the property that had to hold before it could be turned on at all.

## Reproduce

```bash
PY="$PWD/.venv/Scripts/python.exe" bash scripts/verify.sh   # Windows; POSIX: .venv/bin/python
```

Every number above is now recomputed from KLPT's lexicon by
`tests/test_waw.py::test_the_evidence_file_records_real_counts`, including the arithmetic that
must close: `lexicon_entries - waw_initial_words == constructible_joined_forms`, and
`recovered + not_recovered == constructible`. The recall percentage is recomputed too.

> **Corrected 2026-08-09 (D-099).** `waw_initial_words` read **491**; the lexicon has **504**, and
> this file's own `constructible_joined_forms: 24390` proved it — 24 894 − 504 = 24 390, whereas
> 24 894 − 491 = 24 403. The old version of the test bounded three of the seven numbers
> (`lexicon_entries > 20_000`, `dictionary_words_damaged == 0`, and the unsplittable list against
> its own length) and recomputed none, so the wrong figure sat here through two adversarial passes.
> Both passes flagged it and both got the true value wrong in turn — one reported "504 with
> duplicates, 492 distinct"; measured, there are 504 with **zero** duplicates. `lexicon_entries:
> 24894` was right: KLPT's `.dic` is Hunspell format whose first line is an entry count (`24888`,
> itself stale in KLPT's data), and the suite's `lexicon` fixture already skips it.
