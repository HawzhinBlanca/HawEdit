# Adversarial pass on M5.2: the evidence held, the tests did not

Every fifth iteration takes a row marked DONE and tries to prove it false. M5.2 was the newest,
and the attack was not re-reading it — it was breaking each guard one at a time and asking
whether the gate noticed.

## What survived

Every claim in the M5.2 row, re-run from scratch:

```
CLAIM 'index over three scenes'          -> 3 windows, built in 10.1s        (recorded: 10.4s)
CLAIM 'Kurdish query retrieves'          -> ranks [1, 2, 3], scenes [1, 2, 0]
CLAIM 'reranker changes the order'       -> retrieval [1, 2, 0] -> rerank [1, 0, 2]
CLAIM 'scene 0 third to second'          -> scene 0 at rank 2 (was 3)
CLAIM 'retrieval scores carried through' -> True
CLAIM '~8.17 GiB with both resident'     -> 8.17 GiB
CLAIM 'unit-norm vectors'                -> [1.0]
```

The row is accurate. Nothing in it had to be withdrawn.

## What did not survive

Seven guards, mutated one at a time, each with the tree restored from git in between. The
question was not "does the code look right" but "if someone reverted this, would the gate say
so":

| Mutation | Gate |
|---|---|
| `embed_frames`: drop `video_metadata` — **the entire D-049 fix** | **MISSED** |
| `embed_frames`: drop the timestamp assertion | **MISSED** |
| reranker `score`: drop `video_metadata` | **MISSED** |
| reranker `score`: `add_generation_prompt=True` → `False` | **MISSED** |
| reranker `score`: replace D-051's float32 formula with a constant | **MISSED** |
| `rerank`: restate the retrieval score as the rerank score | CAUGHT |
| `rerank`: drop the deterministic tie-break | CAUGHT |

**Five of seven.** Every headline fix of the previous three iterations was silently revertible:
the timestamp fix that stopped a 4.16 s window being stamped 0.1 s, the assertion that catches
it, the answer-position flag the reranker's score depends on, and the precision formula whose
absence was 57% of the rank-1/rank-2 margin.

The cause is a single shape. The tests covered every *refusal reachable without weights* —
recipe missing, pooling unsupported, wrong §7 role, no CUDA — and nothing covered the **wiring**:
which arguments actually arrive at the processor. Those live in the one code path the tests
could not reach, and the evidence files recorded that they *worked once* rather than that they
*keep working*. An evidence file is a measurement of a moment; only a test is a measurement of
every moment after it.

This is the same failure this project has caught in itself repeatedly, one level up: M0.10's
metric with no benchmark behind it, M3.4's `duration_ms` that echoed the request, `encoder_available`
trusting a listing. Here it was the test suite doing the trusting.

## The fix, and why the stub is not a fiction

Four tests now cover the wiring, with a stub processor and model — no weights, so they run on a
CI runner that has never downloaded a checkpoint.

The stub processor **reproduces measured behaviour rather than inventing it**. Given
`video_metadata` as a top-level argument it writes timestamps inside the window; without it, it
writes `<0.0 seconds><0.1 seconds>` — which is exactly what the real processor produced for the
4162 ms window in `evidence/m5-2-video-timestamps.md`. So a mutation that drops the argument
fails here for the same reason it fails on real weights, not for a reason a stub made up.

The score test is arithmetic rather than assertion-on-a-call: `lm_head.weight` rows `[1, 0]` and
`[0, 1]` give direction `[-1, 1]`, the hidden state is `[3, 1]`, so the score must be
`sigmoid(-3 + 1) = sigmoid(-2) = 0.119203`. A constant cannot produce that, and neither can a
mean or a sum.

## Re-audited

```
CAUGHT embed_frames: drop video_metadata (the D-049 fix)
CAUGHT embed_frames: drop the timestamp assertion
CAUGHT reranker score: drop video_metadata
CAUGHT reranker score: add_generation_prompt=True -> False
CAUGHT reranker score: use bfloat16 logits instead of the float32 formula (D-051)
CAUGHT rerank: restate the retrieval score as the rerank score
CAUGHT rerank: drop the deterministic tie-break

unprotected mutations: 0
```

## What this does not cover

The mutation set is seven guards chosen by hand, not exhaustive — a survivor elsewhere in the
module would not show up here. What the pass establishes is narrower and still worth having:
the five specific fixes that three iterations of measurement paid for are now defended by the
gate rather than by a document.

The audit script is `scratchpad/mutate.py` and is deliberately **not** committed: it rewrites
tracked source and restores with `git checkout`, which is safe to run deliberately and hostile
to leave lying in a repository where a `--force` or a dirty tree would lose work.
