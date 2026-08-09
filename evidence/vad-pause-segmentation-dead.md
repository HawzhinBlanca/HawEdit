# §4.2's VAD-pause segmentation has never fired, and cannot

> Measured 2026-08-09 on hawapc01 against `70f38a4`.

M1.2's Definition of Done is *"§4.2 sentence segmentation (Kurdish punctuation **plus** VAD
pauses) + §5 anchors"*. The punctuation half works. The word-gap pause path works. The **VAD-pause**
half is unreachable code.

## The algebra

`pause_follows` (`src/hawedit/sentences.py:104-107`):

```python
def pause_follows(earlier: Word, later: Word) -> bool:
    if later.start_ms - earlier.end_ms >= pause_ms:
        return True
    return any(start >= earlier.end_ms and end <= later.start_ms for start, end in vad_silences)
```

with `vad_silences` filtered to `end - start >= pause_ms`.

The second line is reached only when the first is false — `gap < pause_ms`. For it to return true it
needs a silence with `start >= earlier.end_ms` and `end <= later.start_ms`, so
`end - start <= gap`. Combined with the filter, `pause_ms <= end - start <= gap`, therefore
`gap >= pause_ms` — contradicting the branch it sits behind. **No input can satisfy both.**

## Brute-forced, because algebra is a claim until it is run

```
gap = 100 ms, pause_ms = 400
  no vad pauses            -> 1 sentence
  vad silence 1000..1400   -> 1        400 ms, starting exactly at the first word's end
  vad silence  900..1500   -> 1        spans the gap generously
  vad silence 1000..1100   -> 1        exactly the gap
  vad silence    0..2000   -> 1        spans both words

brute force over every (start, end) on a 25 ms grid across the utterance,
keeping only silences >= pause_ms:
  silences tried: 3528
  splits caused:  0
  -> NONE — the branch is unreachable
```

The control in the same test confirms segmentation itself is not broken: moving the words 500 ms
apart splits them into 2 sentences with no `vad_pauses` at all. So this is specifically the VAD half
being inert.

## It is computed and discarded, not merely unwired

`pipeline.py` derives the silences from Stage 0's real Silero output via `_pauses_between(ingested)`
and passes them into `segment_sentences(..., vad_pauses=vad_pauses)`. They travel the whole way and
have no effect — the same shape as D-070's `natural_silence_ms`, which was computed by the same
helper and dropped before Stage 5. That is twice now that a measurement Stage 0 took has reached a
parameter that ignores it.

## Not fixed, and why that is the honest answer

The containment test is clearly wrong. What should replace it is a decision about Kurdish speech
rather than a refactor, and the two defensible candidates fail in opposite directions:

- **Overlap** — any qualifying silence overlapping the inter-word interval ends the sentence. This
  catches the case the feature exists for: CTC alignment stretches a word across silence, so the
  word timings show a small gap while VAD saw 400 ms of quiet. It risks over-splitting when a long
  silence clips the boundary by a millisecond.
- **Boundary containment** — the silence must span from before `earlier.end_ms` to after
  `later.start_ms`. Conservative; fires only when VAD and the alignment genuinely disagree.

Either changes where Kurdish sentences end, and therefore §5's anchors, every fused boundary and
every rendered clip. There is no labelled Sorani audio on this machine to measure which produces
better boundaries, and §4.2 does not say. Choosing by taste is what the "never guess a threshold"
rule exists to prevent, so it is recorded as `BLOCKED.md` #14 with both options rather than
implemented.

## What was added instead

`test_vad_pauses_currently_cannot_split_a_sentence` pins the measured fact across four silences,
including the one §4.2 would most obviously want to act on. Its docstring says plainly that it
documents a defect rather than a desired behaviour, and that the test going red means the fix
landed — at which point M1.2 is re-statused, `BLOCKED.md` #14 closes, and the test is deleted.

A test that asserts a feature does not work is unusual, and the alternative was worse: leaving code
that reads as if VAD segmentation happens, in a module whose output every clip boundary depends on.

## A caveat about how this was found

The second adversarial pass surfaced it, and that agent's **baseline was red** — a git worktree has
no `.venv`, so `tests/test_gate.py` contributes 9 failures there. It compensated by comparing
failure counts against the known-red baseline, which is weaker than this project's rule that a
mutation audit needs a green baseline first. Everything above was therefore re-derived and
re-measured in the main checkout, where the baseline is green at 1,118, before anything was changed.
Three of the ten agents in that pass had the same red baseline; their other findings are treated as
unverified until measured the same way.

Gate: `VERIFY OK — 1119 passed, 0 skipped`.
