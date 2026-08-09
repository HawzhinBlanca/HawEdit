# Adversarial pass #9 — the reranker, and a query that was the whole episode

> Run 2026-08-09 on hawapc01 against `db63fd2`.
> Target: **M5.2**, DONE — the real `Qwen3-VL-Embedding-2B` / `-Reranker-2B` behind Stage 2.

M5.2 is the row D-053's pass already caught once, when five of seven mutated guards passed the gate
untouched. It is also the row the previous iteration's crash lands on.

## What did not survive — the query

The composed visual run on the real 38-minute file died in Stage 2:

```
$ hawedit ZAR38MinTest.mp4 --transcript … --visual --visual-max-frames 8 --visual-keep 7 --auto-select
✗ CUDA out of memory. Tried to allocate 40.89 GiB. GPU 1 has a total capacity of 23.99 GiB
```

With no `--gemini` there is no verbal candidate, so `pipeline.py` fell the retrieval query back to
`normalized.text_ckb`. Reproduced at the model boundary, driving the real embedder directly rather
than inferring it from the crash:

```
Qwen3-VL-Embedding-2B on cuda:1, weights resident 3.96 GiB, card 23.99 GiB

   chars   tokens  embed_text
     200      167  fits, peak  4.04 GiB
   1,000      755  fits, peak  4.27 GiB
   2,000    1,481  fits, peak  4.56 GiB
   4,000    2,997  fits, peak  5.69 GiB
   8,000    5,988  fits, peak  9.86 GiB
  16,000   11,908  OOM
  35,185   26,191  OOM — tried to allocate 40.89 GiB
```

The last line is this media's real transcript and the figure the pipeline died on, to the digit.

The crash is the loud half. The quiet half is that where the transcript *does* fit — any short media,
including every fixture — retrieval ranks each window against the whole episode. That produces a
Recall@K number §8.2 would read as meaningful. A size limit fixes only the loud half, which is why
the fix is a refusal: §3 Stage 2 retrieves against a query, and a run without one has nothing to
retrieve against. `StageSkipped(blocked_by=("a retrieval query",))`, before any frame is extracted.

## What survived — all seven guards

D-053's seven mutations, re-run on today's tree. The three call sites have since been consolidated
into `window_batch` (D-060), so the mutations moved with them:

```
baseline fails: False

CAUGHT  window_batch drops video_metadata — the whole D-049 fix
CAUGHT  window_batch drops the timestamp assertion (D-049's guard)
CAUGHT  window_batch drops the frame-count assertion (D-060's guard)
CAUGHT  the reranker asks without the answer position (add_generation_prompt)
CAUGHT  D-051's float32 score direction becomes a constant
CAUGHT  rerank restates the retrieval score as the rerank score
CAUGHT  rerank drops the deterministic tie-break

7/7
```

Five of these were **MISSED** in August. D-053's stub-level wiring tests hold, and consolidating the
three call sites into one function did not open a gap.

## What did not survive — a rate the code refuses

M5.2's cell says the evidence index is *"at **3 fps**, not §3's ~1 fps reference"* and, from D-060,
that *"3 fps is the only rate a 1400 ms scene is legal at"*. Measured:

```
SceneWindow(fps=1.0)  ACCEPTED
SceneWindow(fps=2.0)  ACCEPTED
SceneWindow(fps=2.5)  REFUSED — above the 2.0 fps every §7 visual checkpoint declares
SceneWindow(fps=3.0)  REFUSED
SceneWindow(fps=4.0)  REFUSED
```

D-063/D-065 lowered the ceiling to `DECLARED_SAMPLING_FPS = 2.0` and re-measured the index at 2 fps;
the margin moved again, 0.015441 → **0.027870**. `evidence/m5-2-embedder.md` carries that
supersession in a banner at the top of the file. **The ledger cell did not**, so the published tally
still described a run at a rate the code raises on. Corrected in the cell.

The evidence file's own body is left as written: it is a record of a moment, and its banner already
says which moment.

Gate: `VERIFY OK — 1255 passed, 0 skipped`.
