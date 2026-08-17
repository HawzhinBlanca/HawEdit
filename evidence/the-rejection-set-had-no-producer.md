# The rejection set had no producer

> Measured 2026-08-09 on hawapc01 against `f8797f7`.

§5, immediately after the clip contract:

> **Rejection is a first-class outcome.** Every rejected candidate keeps a `reject_reason` and its
> `discovery_path`. That set is your only measure of recall.

§8.2 spends that set: *candidate Recall@20 per discovery path*, and the decision it drives — *"if
Path B never surfaces a winner Path A missed, collapse it."*

## The premise

```
$ grep -rn "RejectedCandidate" src/hawedit tests

src/hawedit/clip.py       the dataclass, its validation, to_dict, from_dict
src/hawedit/transcripts.py  a comment citing it as precedent
tests/test_clip.py        4 construction sites
tests/test_transcripts.py a docstring

constructed in src/hawedit : 0
```

The type is real, validated — a blank `reject_reason` raises, "the rejection set is the only measure
of recall there is, and a blank reason measures nothing" — and unit-tested. Nothing in the program
ever made one. **Never computed**, not computed and discarded.

Meanwhile the runner throws the answer away twice:

* `_automatic_sentence_selection` walks candidates in priority order, computes which complete
  sentences lie wholly inside each, and `continue`s past the ones with none. The reason exists for
  exactly one statement.
* `_candidate_for_judging` builds `containing` — the candidates that hold the selected span — and
  returns the smallest. The rest are dropped.

On the real 38-minute run recorded in D-143: **7 candidates, 1 chosen, 6 with no trace.**

## What was changed

One producer, after the selection settles, so a candidate cannot be recorded under two decisions and
counted twice. The survivor is chosen once now, rather than again inside Stage 4 — which also means
the record exists on a run whose Stage 4 is blocked, and every run on this machine is one of those.

`_complete_sentences_within` is shared between the selector and the reason. Two copies of that
predicate could drift into a rejection claiming *"no complete sentence lies inside it"* about a
candidate the selector would have accepted, and the artifact would be confidently wrong.

## Proof, through the real `run_pipeline`

Three candidates over the real fixture, whose two sentences run 100..1700 and 2000..4100 ms:

```
best    2000..4100  chosen
early      0..1700  out-ranked by survivor best
silent  1700..1950  no complete sentence lies wholly inside this candidate
rejected_by_path    {"verbal": 2}
```

The reasons differ, and they differ *because the code decided differently* — `silent` contains
neither sentence, so eligibility ruled it out before rank ever applied.

Two controls, because the positive test passes for wrong answers:

* **a run that chose nothing rejects nothing** — no judge, no selection. Recording every candidate
  but one would satisfy every positive assertion and be false whenever no decision was made.
* **the empty set and every path are still reported** — `{"visual": 0}` on a run that lost none. An
  absent key reads as a build that does not record rejections (D-145's rule).

```
baseline fails: False

RED  the rejections never reach the run
RED  the chosen survivor is recorded as rejected too
RED  every rejection gets the same generic reason
RED  rejections are recorded even when nothing chose        <- the control
RED  a path that lost nothing is left out of the split
RED  the empty rejection set is omitted rather than reported

6/6
```

## What this could not measure, and why

The intent was a fresh 38-minute number rather than D-143's. That run died in Stage 2:

```
$ hawedit ZAR38MinTest.mp4 --transcript … --visual --visual-max-frames 8 --visual-keep 7 --auto-select

✗ CUDA out of memory. Tried to allocate 40.89 GiB. GPU 1 has a total capacity of 23.99 GiB
```

With no `--gemini` there is no verbal candidate, so the retrieval query falls back to
`normalized.text_ckb` — the **whole 35,185-character transcript**, 6,104 words. A separate defect,
with its own iteration. Recorded here so the missing number is visibly missing rather than quietly
replaced.

One thing that run did prove: the `✗` arrived readable rather than as `\u2717`. D-152 holds.

Gate: `VERIFY OK — 1252 passed, 0 skipped`.
