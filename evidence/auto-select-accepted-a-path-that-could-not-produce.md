# `--auto-select` accepted a Stage 3 producer that could not produce

> Measured 2026-08-10 on hawapc01 against `9e8f128`. Real media: `ZAR38MinTest.mp4` (38 min) and
> `tests/fixtures/kurdish-speech-3cuts.mp4` (4.2 s). ffmpeg 8.1.1-full, Python 3.11 in `.venv`.

## The premise

`main`'s argv block refuses combinations that cannot work — ten of them, including
`--visual-query requires --visual`. One of them was wrong:

```python
if args.auto_select and not (args.visual or args.gemini or args.vertex_project):
    raise ValueError("--auto-select needs at least one Stage 3 producer")
```

§3 Stage 2 retrieves against a query. There are two sources for one — `--visual-query`, or Path A
anchoring one from its best candidate, which needs `--gemini`/`--vertex-project`. D-117 removed the
third (the whole transcript: *"it is not a query — it is the corpus"*, and it asked for 40.89 GiB on
a 23.99 GiB card). So since D-117, `--visual` alone cannot rank a window and cannot answer
`--auto-select`.

## Reproduced on the real 38-minute file

```
$ python -m hawedit.pipeline "…/Test Videos/ZAR38MinTest.mp4" \
    --work-dir …/zar74 --media-id zar38final \
    --transcript work/zar38-final/transcripts/zar38final.transcript.raw.json \
    --visual --timelens --auto-select --qc-pass --json
exit 1     report 1,015,974 bytes

work dir created 07:48:33      last write 07:51:23        → 170 s
  stage0/audio.wav                 74,039,412 bytes  07:49:56
  stage0/proxy.mp4                 51,124,346 bytes  07:50:23   → Stage 0 ≈ 111 s
  stage0/proxy.mp4.provenance.json        653 bytes  07:50:24

complete                        False
skipped                         visual_index, discovery, editorial, boundary, render, delivery
sentence_count                  186
speech_without_transcription_ms 664
visual_windows                  164   (first: zar38final:s0:w0, 0..7920 ms, 2 fps, 16 frames)
candidates                      0
resumed_over                    []

visual_index  §3 Stage 2 retrieves against a query and this run has none: Path A found no
              candidate to anchor one and --visual-query was not supplied…
discovery     Every enabled discovery path ran and returned no candidates…
```

Every §7 visual checkpoint is present on this machine (`Qwen3-VL-Embedding-2B`,
`Qwen3-VL-Reranker-2B`, `VideoChat3-4B`, `TimeLens2-4B` — 27.3 GB, `python -m hawedit.models`), so
this is not a missing-weights refusal. It is a missing *query*, and `argv` settled that before the
first byte moved.

**No checkpoint was loaded.** The composer's embedder loads lazily and Stage 2 skipped before the
first window, so `embeddings/` was never created — the cost here is Stage 0's 111 s of ffmpeg,
PySceneDetect and Silero on a 38-minute source, not GPU time. Stated precisely because the
temptation is to call it worse than it is.

## Reproduced on the fixture, with a control that discriminates

```
--visual --auto-select (no query, no gemini)     exit 1    3.5 s
   visual_index: §3 Stage 2 retrieves against a query and this run has none…
   candidates: 0   skipped: visual_index, discovery, editorial, boundary, render, delivery

--visual --auto-select --visual-query ڕۆژنامەوان  exit 1   14.0 s
   visual_index: visual retrieval refused this media: the index holds 3 windows and 7 survivors…
   candidates: 0
```

The second case takes four times as long because it *runs*: it loads the embedder, embeds, retrieves
and then refuses for a reason about this media rather than about the flags. That is what makes the
first case a statement about the missing query.

## The fix

```python
stage_3_can_produce = bool(args.gemini or args.vertex_project) or bool(
    args.visual and args.visual_query
)
if args.auto_select and not stage_3_can_produce:
    raise ValueError("--auto-select needs a Stage 3 producer that can actually produce: …")
```

`--visual` alone is still accepted when `--auto-select` is not asked for: that run reports an honest
`visual_index` skip and is a legitimate thing to want. `_STAGE_3_DISCOVERY`'s runtime message, which
said *"--visual for composed Path B"* and would send a reader straight back into the run above, now
names `--visual-query` and says why it is not optional.

## Proof

```
baseline green: True

RED  the defect restored: --visual alone counts as a Stage 3 producer
RED  the producer test stops running at all
RED  the producer test refuses everything, so no --auto-select run can start
RED  --visual-query stops being a query, so only Path A can produce
RED  Path A stops counting, so --gemini alone is refused
SURVIVED  --visual-query counts even without --visual
RED  the runtime skip goes back to telling the reader --visual is enough

6/7
restored and green: True
```

**The survivor is a bad mutation of mine.** Dropping the `args.visual` conjunct changes no reachable
behaviour: `--visual-query requires --visual` refuses four lines earlier, measured —

```
$ … --transcript x.json --visual-query q --auto-select
✗ --visual-query requires --visual        exit 2
```

so the mutated state cannot be reached and the mutation asserts nothing. Fourth such mutation this
session, after D-137's retry ceiling, D-141's `revisions.json` and D-144's `PARTIAL` row. It did
find something real: that earlier refusal had no test at all, so the ordering the new expression
leans on was held by nothing. It is held now.

Three of the six caught mutations are controls pulling opposite ways — one that refuses every
`--auto-select` run and one that refuses none both go red — so the guard cannot be satisfied by
being uniformly strict or uniformly lax.

Gate: `VERIFY OK — hawedit gate green`, 1440 tests (floor 1434 → 1440).
