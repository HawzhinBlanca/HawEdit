# The report shared stdout with a library

> Measured 2026-08-09 on hawapc01 against `f0bff1d`.
> Source: `ZAR38MinTest.mp4`, the real 38-minute Sorani file.

This run was for something else. D-118 had just given Path B a per-window failure path, and the
question was whether the composed visual stage could finish on real media at all. It did — and the
report was unreadable.

## The defect

```
python -m hawedit.pipeline ZAR38MinTest.mp4 --transcript … \
    --visual --visual-query "میدیای کوردستان" --visual-max-frames 8 --visual-keep 7 \
    --auto-select --json > report.json

report.json                    1,140,793 bytes
bytes before the JSON begins         580
lines of foreign output                2
json.loads(whole file)         JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

The two lines:

```
🚨 `image_grid_thw` is part of VideoChat3ForConditionalGeneration.forward's signature, but not
   documented. Make sure to add it to the docstring of the function in …/modeling_videochat3.py.
🚨 `video_grid_thw` is part of VideoChat3ForConditionalGeneration.forward's signature, but not …
```

Traced, not guessed: `transformers/utils/auto_docstring.py:1602` is
`print("\n".join(undocumented_parameters))`. A bare `print`, so no verbosity setting reaches it, and
loading VideoChat3's remote code fires it twice.

A dependency that prints is the ecosystem's business. Owning the stream a documented contract writes
to is ours — this is D-115's channel again, one layer up: that fixed which *codec* stdout uses, this
fixes who may *write* to it.

## The fix

`cli.machine_readable_stdout()` yields the real stdout and redirects the ambient one to stderr while
it is held. `main` became a four-line front over `_run_from_args(args, report_stream)`, so the body
keeps its indentation and the report goes to the stream it was handed. `editorial_bench` gets the
same treatment: it prints a document to stdout and loads the same stack.

## Proof, on the artifact

The real `main`, in a subprocess, with `run_pipeline` wrapped to print to stdout mid-run:

```
stdout parses as JSON            : yes, media_id present
🚨 in stdout                     : no
🚨 in stderr                     : yes
human mode still writes stdout   : "media   kurdish-speech-3cuts"
exit code on an incomplete run   : 1
```

Two controls, because the positive test passes for wrong answers: redirecting unconditionally would
silence the readable report, and holding the stream must not swallow the return value automation
reads.

```
baseline fails: False

RED  the report shares stdout again (the defect)
RED  the helper redirects but hands back the redirected stream
RED  the helper does not redirect at all
RED  the human report is redirected too              <- control
RED  holding stdout swallows the exit code           <- control
RED  editorial_bench prints its document to the shared stdout

6/6
```

## What the run itself showed — the composed path finished on real media

Recorded here because it is the first time, and because D-118 is what made it possible:

```
indexed_windows : 641
retrieved       :  50
survivors       :   7      rerank 0.244822 … 0.079547
unreadable      :   2      s2:w4 (rank 1) and s129:w2 (rank 6)
candidates      :   5      ranks 1..5 dense, each carrying a real SV6D
discovery       : ran, by_path {"visual": 5}
```

**The rank-1 survivor was one of the two unreadable ones** — 0.2448, nearly three times the next
score. Before D-118 that single refusal discarded all seven; here it costs one candidate and is named
in the artifact with its bounds and its reason.

## And what it did not do: `--auto-select` chose nothing

Not a defect, and worth stating precisely rather than loosely:

```
complete sentences in the media : 185   shortest 0.41 s, median 6.56 s, longest 102.52 s
candidate windows               : 3.38 – 3.88 s (8 frames at 2 fps)
complete sentences lying wholly inside each candidate:
  s9:w5    0        s15:w6   0        s55:w1   0        s61:w1   0        s105:w3  0
sentences short enough for a 3.38 s window at all : 54 of 185
```

So it is not arithmetically impossible — a third of the sentences would fit — but none of these five
windows happens to contain one, so `_automatic_sentence_selection` had nothing to anchor and D-116's
rejection set is correctly empty: nothing chose, so nothing was rejected. The retrieval unit being
~3.5 s rather than §3's ~32 s is `BLOCKED.md` #17, refreshed with this measurement.

Gate: `VERIFY OK — 1268 passed, 0 skipped`.
