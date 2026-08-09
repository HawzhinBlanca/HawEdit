# Adversarial pass #19 — M2.1's text index

> Measured 2026-08-10 on hawapc01 against `9f62f10`, on the real
> `ZAR38MinTest.transcript.norm.json` (6,104 words, 35,185 chars, 186 sentences).

M2.1 is **DONE** for *"§2 text index: BM25 + character 3-grams over normalized Sorani"*, and the
cell's claims are: the clitic failure is measured at word BM25 **0.0**, n-grams retrieve it, and
invariant #3 is enforced at the index boundary.

## The headline claim survives

```
query کتێب against a document containing کتێبەکەم
  d1  total 0.914954   word 0.000000   ngram 1.829909
```

Exactly as written. Word BM25 scores the stem query zero; the n-gram field is what retrieves it.

## What the runner actually built

`pipeline.py` built `Bm25Index.from_transcript(normalized)` — **one document for the whole
episode** — three lines before it computed `sentences`.

```
from_transcript (what the runner built)     from_sentences (what existed, unused)
  documents                   1               documents                   186
  distinct word terms      2,784               distinct word terms      2,784
  distinct idf values          1               distinct idf values         37
  idf range         0.287682..0.287682         idf range      0.855352..4.825644
  average doc length   6,123.0 tokens          average doc length    32.9 tokens
```

BM25's idf is `log(1 + (N - df + 0.5)/(df + 0.5))`. At N=1 every term has df=1, so every term's idf
is `log(1 + 0.5/1.5) = 0.287682`. **One value for 2,784 terms.** Rarity — the thing §2's paragraph
is about — carries no information at all, length normalization compares the document to itself, and
one document is the most any query can return.

Which is what searching it did:

```
  whole  کوردستان     1 hits   scores 2.933   windows 322-2313729
  whole  هەولێر       1 hits   scores 2.244   windows 322-2313729
  whole  زۆر          1 hits   scores 1.556   windows 322-2313729
  whole  سلێمانی      1 hits   scores 1.939   windows 322-2313729
```

Every hit's window is 322..2,313,729 ms — **the whole 38.6 minutes**. §3 Stage 5 consumes a window.

## After

```
runner's index now: 186 documents, 2,784 terms, 37 distinct idf values, range 0.855352..4.825644
average document length: 32.9 tokens
the emitted report's index section:
  {"document_count": 186, "ngram_size": 3, "ngram_weight": 0.5}

  کوردستان
      ZAR38MinTest#38    score  11.545  window   450,274..  465,438 ms ( 15.2 s)
      ZAR38MinTest#162   score  10.927  window 2,164,354..2,176,446 ms ( 12.1 s)
      ZAR38MinTest#119   score  10.521  window 1,816,930..1,819,710 ms (  2.8 s)
  هەولێر
      ZAR38MinTest#122   score  11.779  window 1,824,866..1,854,238 ms ( 29.4 s)
      ZAR38MinTest#130   score   9.660  window 1,889,634..1,907,806 ms ( 18.2 s)
      ZAR38MinTest#121   score   9.186  window 1,822,530..1,824,158 ms (  1.6 s)
  سلێمانی
      ZAR38MinTest#56    score  10.534  window   804,738..  840,382 ms ( 35.6 s)
      ZAR38MinTest#150   score   3.940  window 2,041,154..2,043,614 ms (  2.5 s)
      ZAR38MinTest#133   score   2.540  window 1,919,458..1,925,630 ms (  6.2 s)

widest window any hit can hand Stage 5: 102,524 ms of a 2,313,729 ms media (4.43%)
```

## The second finding — D-090's sibling

D-090 fixed `scored[:k]` in `visual_index.retrieve` and wrote down why: *"a negative `k` drops the
tail instead of keeping a head"*. `Bm25Index.search` ends in `hits[:limit]`. Measured on a
10-document index, before the guard:

```
limit=  10  ->  10 hits   d0,d1,d2,d3,d4,d5,d6,d7,d8,d9
limit=   3  ->   3 hits   d0,d1,d2
limit=   1  ->   1 hits   d0
limit=   0  ->   0 hits
limit=  -1  ->   9 hits   d0,d1,d2,d3,d4,d5,d6,d7,d8
limit=  -5  ->   5 hits   d0,d1,d2,d3,d4
limit= -10  ->   0 hits
limit= -20  ->   0 hits
```

And on a ranked index, so the semantics are visible: `limit=-1` returned `best, mid` and dropped
`worst`. A plausible answer that is silently a different operation.

## Proof

```
baseline green: True

RED  the runner is back on the single-document index (the defect)
RED  from_sentences indexes the whole transcript as one document instead
RED  a sentence hit carries the whole media's window rather than its own
RED  invariant #3's type guard is dropped from the factory the runner uses
RED  the sentence text is indexed raw instead of normalized (invariant #3)
RED  a limit that cannot return a document is accepted again (D-090's sibling)
RED  the limit guard is over-strict and refuses the tight boundary

7/7
restored and green: True
```

The last is the control: `limit=1` is the tight boundary and a guard at `limit < 2` would look
correct while refusing the commonest single-result query. D-090 recorded the same asymmetry.

## Two of my own claims were wrong, and the tests caught them

The first version of `test_a_single_document_index_has_one_idf_and_cannot_rank` asserted that a
rare and a common term score *equally* in the single-document index. They do not — `0.287682` vs
`0.395563` — because term **frequency** still varies within the one document even when idf cannot.
The same mistake was in the second test's control. Both now assert what a single document actually
cannot do: return more than one document, or a window narrower than the media. The overstatement
was also in `index.py`'s docstring and `pipeline.py`'s comment ("nothing can outrank anything") and
is corrected in both.

## What is still open

`Bm25Index.search` has **no production caller**:

```
$ grep -rn "\.search(" src/
src/hawedit/clip.py:102:            if not _TIMESTAMP.search(label):
```

The runner builds the index, reports `document_count`, `ngram_size` and `ngram_weight`, and never
queries it. §3 Path A is explicit — the judge reads *"the **full normalized Sorani transcript** in
one pass. Not a filtered subset"* — while §9's M2 row describes a *"transcript → BM25 → Gemini"*
slice. Those disagree about what the text index is for, and the answer decides what §8.2's per-path
Recall@K measures. `BLOCKED.md` #18, for Hawa. Not invented here.

Gate: `VERIFY OK — hawedit gate green`, 1343 tests.
