# Adversarial pass 19: BM25 had one document and therefore nothing to rank

Date: 2026-08-10. Readiness decision: D-164. Upstream decision: D-134.

## Measured defect

On the real 38-minute transcript (6,104 words, 186 sentences):

| index shape | documents | distinct terms | distinct IDF values | hit window |
|---|---:|---:|---:|---|
| whole transcript | 1 | 2,784 | 1 | 322..2,313,729 ms |
| sentences | 186 | 2,784 | 37 | one sentence |

With one document, every query can return only the same whole-episode window. The sentence index's
IDF range was 0.855352..4.825644 and its widest window was 102,524 ms, 4.43% of the source rather
than 100%.

## Integrated contract

The runner segments first and calls `Bm25Index.from_sentences(sentences, normalized)`. The factory
holds invariant #3 by accepting a normalized transcript, then derives the media id and normalizes
each raw sentence surface internally. Nonpositive result limits fail before slicing.

Focused readiness verification: 146 index/pipeline tests passed with Ruff and strict mypy clean.
The full canonical and exact-SHA gates are recorded only after this integration receives them.

## Honest residual

`Bm25Index.search` has no production caller. `BLOCKED.md` #18 gives the specification conflict and
the labelled acceptance experiment needed before retrieval can be inserted into Path A without
silently changing recall or model context.
