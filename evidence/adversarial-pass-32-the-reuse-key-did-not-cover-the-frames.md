# Adversarial pass 32 — the reuse key did not cover the frames

**Target:** `_EmbeddingCache`'s claim, in its own docstring, that

> Reuse is verified rather than assumed, on everything that changes the vector

**Verdict: REFUTED**, on real footage.

## The attack

The docstring lists three things the key covers: the window, the model id and revision, and the
source digest. `discover` consults the cache **before** extracting any frames — that is the whole
point, 95.1 ms of ffmpeg per window — so the key cannot describe the pixels directly. It has to
describe the settings that produce them, and one of those was missing.

`extract_window_frames` trims what ffmpeg delivered to a multiple of `TEMPORAL_PATCH_FRAMES`:

```python
if len(paths) % TEMPORAL_PATCH_FRAMES and len(paths) > TEMPORAL_PATCH_FRAMES:
    paths = paths[: len(paths) - len(paths) % TEMPORAL_PATCH_FRAMES]
```

D-190 defines that constant as `max()` over the §7 checkpoints' declared `temporal_patch_size`.
It is not a magic number somebody would have to decide to edit — **it moves when the model set
moves.** Add a checkpoint declaring 4, and every cached vector on disk becomes a vector of frames
the model will no longer be shown.

## The measurement

`ZAR38MinTest.mp4`, 82,446,418 bytes, real ffmpeg, real jpgs. No model is needed: the question is
whether the key can tell two frame sets apart.

```
window        : zar38:s2:w0  60000..77500 ms @ 2.0 fps, plans 35 frames

TEMPORAL_PATCH_FRAMES=2 (committed)                        -> 34 frames, pixels 387be9116d335d85…
TEMPORAL_PATCH_FRAMES=4 (a §7 set whose strictest patch is 4) -> 32 frames, pixels 51a2cbdf826a26b2…
the frames handed to the embedder differ: True

the whole reuse key, for BOTH extractions:
  window: {'window_id': 'zar38:s2:w0', 'media_id': 'zar38', 'scene_index': 2, 'window_index': 0,
           'in_ms': 60000, 'out_ms': 77500, 'fps': 2.0, 'frame_count': 35}
  model_id: Qwen3-VL-Embedding-2B
  revision: main
  source_sha256: bd004519e4ed0254f5c4f5197aa501acc56ce957829f62ac0bdc4d7190ec1dd2
```

Two different pixel sets, one byte-identical key. The cache would have served the 34-frame vector
for the 32-frame extraction, and every stage downstream — retrieval, rerank, the reader — would
have worked from an embedding of footage it was not describing.

**The window's own `frame_count` does not cover this**, and that is the part worth noticing: it
records **35**, the *planned* count, which neither extraction produced. It is arithmetic over
`duration_ms` and `fps`, computed before ffmpeg ran. The key contained a number about the frames
and still could not tell the frames apart.

## The fix

One entry in the record, read from the module that does the trimming rather than re-imported, so
the fingerprint is the value actually applied:

```python
"temporal_patch_frames": video_input.TEMPORAL_PATCH_FRAMES,
```

`load` compares the whole record, so entries written before this key existed simply fail to match
and are re-embedded once — the expensive answer, never the wrong one, which is the behaviour the
cache already documents.

**The docstring is corrected rather than left aspirational.** It now names what the key covers and
states what it does not: the ffmpeg invocation itself. A change to the filters or the output
quality would produce different pixels under an unchanged fingerprint. That is code rather than
data, it is not fingerprinted anywhere in this repo's on-disk caches, and saying so is better than
a claim that reads as total and is not.

## Mutation audit — 3/3

```
baseline: GREEN (1630 passed, 86 warnings in 144.28s)

CAUGHT   the frame trim leaves the reuse key entirely
         by 2: test_a_changed_frame_trim_re_embeds,
               test_the_frame_trim_is_recorded_in_the_cache_entry
CAUGHT   the fingerprint is hardcoded instead of read from the module that trims
         by 1: test_a_changed_frame_trim_re_embeds
CAUGHT   load stops comparing the record it wrote  [lint dirty]
         by 7: test_a_changed_frame_trim_re_embeds, test_a_different_checkpoint_revision_re_embeds,
               test_a_replaced_source_re_embeds, …

file restored byte-identical: True
3/3 caught
suite after restore: GREEN
```

The second mutation is the one that justifies reading the constant through the module object: a
hardcoded `2` is *correct today* and still wrong, and only the behavioural test notices. The
artifact test alone would have passed it.

**The first run of this audit was worthless and said 3/3 anyway.** Every mutation came back
`[lint dirty]`, because deleting the record entry leaves `video_input` imported and unused — and
`tests/test_gate.py` runs the *real* `verify.sh`, lint step included. So `test_nested_fast_run_is_
still_allowed` and two of its neighbours failed on the mutation's tidiness rather than on the
guard, and they were sitting in the CAUGHT lists next to the genuine defenders. Re-run with each
mutation dropping the now-unused import, the first two mutations are clean and fail by exactly the
two tests written for them. This is pass 30's lesson arriving from a new direction: *check which
test failed, not that one did.* The third stays lint-dirty — neutering the comparison leaves
`expected` unbound-but-assigned — and is reported that way; it is a sanity check on behaviour that
predates this pass, and its seven defenders include the three dedicated reuse tests.

## The gate caught what a targeted run could not

`pytest tests/test_visual_pipeline.py` passed on a program mypy rejects. Reading
`video_input.TEMPORAL_PATCH_FRAMES` from another module is an implicit re-export, which this repo
forbids:

```
Module "hawedit.video_input" does not explicitly export attribute "TEMPORAL_PATCH_FRAMES"
[attr-defined]
Found 1 error in 1 file (checked 99 source files)
```

Nothing in the visual tests could see that. What surfaced it was the *baseline* of this audit going
red on four `test_gate.py` tests, which invoke `scripts/verify.sh` as a subprocess and therefore
run lint and typecheck as part of the suite. Fixed by declaring the re-export in `video_input`'s
`__all__` rather than by re-importing the constant from `visual_index` — the value the cache must
record is the one the trimming module applies, and making that a declared part of its contract says
so.

`test_a_second_pass_reuses_every_embedding_and_extracts_no_frames` is the control this pass leans
on throughout — it asserts 12 embeddings and no second extraction when nothing changes, so "24
embeddings" means the trim was noticed, rather than the cache having stopped working.

## What survived

Everything else in the docstring's list. The window, revision and source-digest keys each have a
test that reverts them and goes red, and all three were re-run here as part of the audit's third
mutation. The claim was not wrong about what it did; it was wrong about being complete.
