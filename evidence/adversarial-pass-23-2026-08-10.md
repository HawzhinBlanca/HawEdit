# Adversarial pass #23 — M5.2, and Kurdish invariant #3 in Stage 2

> Measured 2026-08-10 on hawapc01 against `2fd2e55`, Python 3.11 in `.venv`. No weights needed:
> every measurement below runs on CI, where `models/` does not exist.

`PROGRESS.md` M5.2 is **DONE**: the real `Qwen3-VL-Embedding-2B` and `-Reranker-2B` behind the
Stage 2 interfaces. The row is heavily evidenced — three files, a real GPU run, a recorded fps
deviation. This pass tried to prove it false.

## What survived

* The three cited evidence files exist: `m5-2-embedder.md` (7,610 bytes), `m5-2-reranker.md`
  (6,840), `m5-2-frames-reaching-the-model.md` (9,241).
* README's three claims for `qwen_visual.py` each still have a test that reddens when reverted:
  pooling read from the checkpoint (`does not state how`), §7 role checked before the weights load
  (`cannot be used as the visual embedding model`), no silent CPU fallback (`reports no CUDA`).

The row does not overclaim. What it never claimed is where the hole was.

## What did not survive

Both Stage 2 adapters normalize the query before the model reads it — `QwenVisualEmbedder
.embed_text` and `QwenVisualReranker.score` — and both docstrings explain why. Removing either
call, one at a time, against a baseline verified green first, whole gate suite each time:

```
baseline green: True

UNHELD  the embedder stops normalizing the query (invariant #3)
UNHELD  the reranker stops normalizing the query (invariant #3)

restored and green: True
```

Static confirmation of why: `tests/test_qwen_visual.py` never mentioned normalization;
`embed_text` was called by no test at all; and the two tests that call `score` pass
`"ڕۆژنامەوانی"`, which is already §4.1-normalized — so in the only place the call ran, it was a
no-op.

## What it costs

§4.1's collisions are what an Arabic keyboard produces. Measured on the codepoints:

```
'كوردي'      -> 'کوردی'   0x643 -> 0x6a9  (Arabic kaf  -> Kurdish kaf)
                          0x64a -> 0x6cc  (Arabic yeh  -> Kurdish yeh)
'ده\u200cست'  -> 'دەست'    ZWNJ dropped,  0x647 -> 0x6d5
'٢٠٢٦'       -> '2026'    Arabic-Indic   -> ASCII
```

None of it raises. The query embeds, the reranker scores, every number stays in range, and Stage 2
retrieves against a different alphabet from the one the corpus was indexed in.

## The fix

`StubProcessor` records the conversation as well as the kwargs — invariant #3 is a claim about the
text the model was asked to read, and the return value cannot show it, because a wrong-alphabet
query still produces a vector and still produces a score in [0, 1].

One query carries four collisions at once, and the assertions name the codepoints: `0x643`,
`0x64a`, ZWNJ and Arabic-Indic digits must all be absent from what reached the model, and the
normalized form must be present. `_classes_taking_a_query()` reads the module for every class with
a method taking a `query` and compares that set to `_STAGE_2_QUERY_READERS` **both ways**, so a
third adapter fails until someone says how to drive it.

The control is idempotence: an already-normalized query must arrive byte-identical, so an adapter
that mangled or dropped every query — which would satisfy the first test — fails.

## Proof

```
baseline green: True

RED  the defect restored: the embedder stops normalizing the query
RED  the defect restored: the reranker stops normalizing the query
RED  the embedder sends the raw query beside the normalized one
RED  the reranker sends the raw query beside the normalized one
RED  the embedder drops the query entirely
RED  the reranker drops the query entirely
RED  the enumeration stops naming the reranker, so its half is unheld again
RED  the enumeration stops naming the embedder

8/8
restored and green: True
```

## A third mutation that is not a result

Removing *both* calls at once reported `held`. It is not a measurement: with `normalize_sorani` no
longer used, the import is dead, ruff raises F401, and the nested-gate test fails on **lint**
rather than on the tests — the same contamination as D-148's SIM223, one session apart. The probe
printed `[lint dirty]` beside that line, and the audit now strips an import a mutation orphans.
A result the tooling cannot vouch for should say so on the line where it is printed.

Gate: `VERIFY OK — hawedit gate green`, 1471 tests (floor 1466 → 1471).
