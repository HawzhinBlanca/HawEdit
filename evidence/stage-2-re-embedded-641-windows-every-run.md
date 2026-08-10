# Stage 2 re-embedded 641 windows on every run

> Measured 2026-08-10 on hawapc01 (2× RTX 3090 Ti) against `e677f29`, on
> `C:\Users\Wareen\Desktop\Test Videos\ZAR38MinTest.mp4`.

D-132 made Stage 0 re-runnable and D-136 Stage 1. Stage 2's visual half is bigger than either.

## Before

```
Stage 0 on ZAR38MinTest.mp4: 2,313,800 ms, 138 shot cuts
Stage 2 plans 641 scene windows at 2.0 fps, max 8 frames

frame extraction of 12 windows:
  first pass     1.14 s   (  95.1 ms/window)
  second pass    1.11 s   (  92.3 ms/window)
  jpgs on disk 81   rewritten by the second pass: 81
  -> extrapolated over 641 windows: 60.9 s

loading the real Qwen embedder from …\models\Qwen3-VL-Embedding-2B on cuda:1 …
  embedding 12 windows:  38.49 s (3207 ms/window)
  -> extrapolated over 641 windows: 2055.9 s
```

`discover` built a fresh in-memory `_FrameCache` per call and embedded every window
unconditionally. `extract_window_frames` runs ffmpeg with `-y`, which is why **all 81 jpgs were
rewritten**.

## After

```
pinned embedding revision: 9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda
source sha256: bd004519e4ed0254…

first pass       16.49 s   embedder calls this pass: 12
second pass       0.14 s   embedder calls this pass: 0

cache files written: 12
cached vectors bit-identical to the fresh ones: True
embedder calls: 12 then 0
per-window embedding: 1374 ms
extrapolated over 641 windows: 880.7 s first run, 7.5 s on a re-run
```

**12 calls then 0**, and the vectors match bit for bit. Two per-window figures appear above because
the first measurement's 12 windows included the model's first forward pass (3,207 ms) and the second
ran warm (1,374 ms); both are stated rather than the flattering one.

One file per window, so a run killed at window 400 of 641 keeps 400.

## Proof

```
baseline green: True

RED  every window is embedded again, cache ignored (the defect: 880.7 s redone)
RED  nothing is ever stored, so the next run has nothing to reuse
RED  frames are extracted even for a cached window (the 95.1 ms/window)
RED  the checkpoint revision is dropped from the key, mixing embedding spaces
RED  an unidentified checkpoint reuses its own unnamed vectors
RED  the source digest is dropped, so another recording's vectors are served
RED  the window's own identity is dropped from the key
RED  a stored record is trusted without comparing it to what this run expects
RED  a cached vector skips the embedding invariants (a zero vector is served)
RED  the cache writes one combined file, so a killed run keeps nothing
RED  the record is written in place, so a killed write leaves a half-record
RED  the runner stops passing the pinned revision to the composer

12/12
restored and green: True
```

**The first pass was 10/12.** Both survivors were the same shape as D-105, D-133 and D-135: the
staged write had no test in which a write actually failed, and the runner's `embedding_revision=`
argument could be dropped with every test green — unheld wiring, for the fourth time.

## Two things my own code and my own test got wrong

**The code did not implement the rule its docstring stated.** An empty revision means "not pinned",
and it compared equal to itself — so unpinned weights reused their own unnamed vectors. Caught by
the test written for the rule rather than for the code.

**The test asserted a guarantee the design cannot give.** A hand-edited *vector* that still parses
and still satisfies the embedding invariants is indistinguishable from a legitimate one: validating
the content means re-embedding it, which is the cost the cache exists to avoid, and any checksum
beside it is derived from the same file. Truncation — the realistic corruption — *is* caught, and
the test now says only that. The limitation is recorded, not hidden.

Gate: `VERIFY OK — hawedit gate green`, 1393 tests.
