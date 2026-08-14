# Stage 2 query normalization is observed at every model input

> Integrated 2026-08-10 from protected-main finding `ba2a445`; readiness test fix
> `62a9e63`. Production `src/hawedit/qwen_visual.py` was already correct and remained unchanged.

## The silent failure

`QwenVisualEmbedder.embed_text` and `QwenVisualReranker.score` normalize their query before the
model reads it. Removing either normalization call independently left protected main's complete
gate green. The existing score tests used an already-normalized query; `embed_text` had no direct
model-input test. A wrong-alphabet query still returns a unit vector and a score in `[0, 1]`, so
output-shape assertions cannot see the defect.

That violates Kurdish invariant #3 in the retrieval stage. Window text is normalized before
indexing, so a raw query compares a different alphabet against the corpus while producing entirely
plausible numbers.

## Discriminating input

One query carries four real §4.1 keyboard collisions:

- Arabic kaf U+0643, which normalizes to Kurdish kaf U+06A9;
- Arabic yeh U+064A, which normalizes to Kurdish yeh U+06CC;
- ZWNJ before Arabic heh, folded to Kurdish ae; and
- Arabic-Indic `٢٠٢٦`, normalized to ASCII `2026`.

The processor stub now records the complete conversation the model was asked to read. For both the
embedder and reranker, tests require normalized text to be present, the raw query absent, the raw
codepoints absent, and ASCII digits present. This observes the invariant at the model boundary
rather than inferring it from a vector or score.

## Future adapter binding and control

An introspection check enumerates every production class in `hawedit.qwen_visual` with a method
that accepts `query` and compares that set bidirectionally with the driver table. A third adapter
therefore fails until its actual model-input path is tested. The positive control sends an already
normalized query and requires it to arrive unchanged, preventing a query-dropping or uniformly
mangling adapter from satisfying the negative assertions.

Focused acceptance: 95/95 across Qwen visual, composed visual pipeline and Path B tests; Ruff clean;
strict mypy clean for `src/hawedit/qwen_visual.py`. Protected main measured the corresponding
mutation set at 8/8 after adding equivalent behavioral distinctions; this branch relies on its
adapted tests and the canonical whole-repository gate rather than restating that run as local.
