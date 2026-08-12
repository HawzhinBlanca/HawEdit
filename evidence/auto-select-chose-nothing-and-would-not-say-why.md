# `--auto-select` chose nothing and would not say why

The composed pipeline runs to completion on the real 38-minute file and produces **no clip**. That
is not a defect — but the report gave the operator no way to know it, because the only thing it
said was the symptom:

```
SKIPPED boundary [complete selected sentences]: boundary did not run because complete
        selected sentences was not available.
```

which reads as a broken selector. The cause is arithmetic between two numbers the run already
holds.

## The measurement

Champion transcript, 7 Path B candidates, on the real file:

| | |
|---|---|
| Candidates | 7, spanning **3.48–3.96 s** |
| Complete sentences | 184, running **0.41–102.52 s**, median **6.72 s** |
| Short enough in principle | 57–63 per candidate |
| **Wholly inside any candidate** | **0** |

§5 selects complete sentences *wholly inside* a candidate, so a retrieval unit shorter than a
sentence can contain none however good the retrieval was. Per candidate:

```
zar38champion:s0:w0        0.00–   3.96s   wholly inside: 0   short enough in principle: 63
zar38champion:s0:w1        3.96–   7.92s   wholly inside: 0   short enough in principle: 63
zar38champion:s54:w4    1040.29–1043.82s   wholly inside: 0   short enough in principle: 57
zar38champion:s60:w3    1151.37–1155.26s   wholly inside: 0   short enough in principle: 63
zar38champion:s60:w4    1155.26–1159.16s   wholly inside: 0   short enough in principle: 63
zar38champion:s60:w8    1170.85–1174.74s   wholly inside: 0   short enough in principle: 63
zar38champion:s67:w1    1269.92–1273.40s   wholly inside: 0   short enough in principle: 57
```

## Why the windows are 3.5 s, from the code's own arithmetic

`_max_window_ms` is `floor(max_frames * 1000 / fps)` — the window ceiling is `max_frames / fps`:

| setting | window |
|---|---|
| §3's blueprint: 64 frames @ 2.0 fps | **32.0 s** |
| this machine: 8 frames @ 2.0 fps | **4.0 s** ← what ran |
| this machine: 8 frames @ 1.0 fps | 8.0 s |
| this machine: 8 frames @ **0.25** fps | **32.0 s** |

`BLOCKED.md` #17 / D-108 record that `MCG-NJU/VideoChat3-4B` reads at most **8** frames per window
on this 24 GB 3090 Ti, and that lowering the ceiling "changes what a window *is*". What that entry
does not say, and this measurement adds, is that the ceiling constrains the **product**
`max_frames / fps` and therefore the window *duration* — so §3's ~32 s retrieval unit is reachable
on this card at a lower sampling rate, trading temporal resolution for window length.

**No default is changed here.** `DECLARED_SAMPLING_FPS = 2.0` is a declared constant and §8.2's
Recall@K is measured on whatever unit it produces; picking a new rate is a threshold decision with
real cost, and this loop does not guess thresholds. The option and its measured trade are recorded
for whoever makes that call.

## The fix

The boundary skip now states the cause instead of the symptom, in the numbers the run already has:

```
--auto-select examined 7 candidate(s) spanning 3.48–3.96s and found no complete sentence
wholly inside any of them. The transcript has 184 complete sentence(s) of 0.41–102.52s,
median 6.72s. A candidate window holds max_frames/fps seconds, so a lowered frame ceiling
shortens the retrieval unit — see BLOCKED.md #17.
```

Same family as D-111 and D-183: a step that decided something reported nothing about the decision.

## Mutation audit — 5/5 lint-clean

```
CAUGHT   auto-select goes back to the symptom, saying only that sentences were unavailable
CAUGHT   the candidate spans are dropped, leaving half the arithmetic
CAUGHT   the sentence lengths are not the transcript's, so the other half of the cause is wrong
CAUGHT   the median is computed but never stated
CAUGHT   the pointer to the frame ceiling is dropped, leaving numbers with no next step

file restored byte-identical: True
5/5 caught lint-clean
suite after restore: GREEN
```

Two controls: a candidate wide enough to hold a sentence must select normally and carry no such
reason, and a run without `--auto-select` must still say exactly what it said before — this
explanation belongs to auto-select, and one attached unconditionally explains nothing.

**One equivalent mutant, reported rather than counted.** Attaching the explanation
unconditionally (`if not automatic:` → `if True:`) survives, and no test can catch it: on every
path where a selection succeeds, `run.boundary` is overwritten downstream, so the two programs are
observationally identical. Verified directly by applying the mutation and re-running the
wide-window case — clip still produced, boundary still unskipped. The guard is kept as
`if not automatic:` because it is intention-revealing and does not build an object that will be
discarded, not because a test defends it.

**Two of the first-run mutations were lint-dirty and did not count**: deleting an assignment while
the f-string still referenced the name is a *broken program*, not a mutation. Rewritten to
substitute values (`spans = [0, 0]`, `lengths = [0]`), which required the test to assert the span
values and the median *value* rather than the word "median". First run 2/5, then 3/5, then 5/5.
