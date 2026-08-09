# Adversarial pass #6 â€” the artifacts that ship to a client

> Run 2026-08-09 on hawapc01 against `3ad7157`, against a green 1,181 baseline.
> By hand, one mutation at a time, each reverted before the next.

Two consecutive iterations had found the same class â€” a written artifact whose renderer nothing read
(D-126's Â§8.1 report JSON, D-132's readiness text). SRT, EDL and `editing.json` are the files an editor
actually opens, so they got the same treatment.

## Part 1 â€” SRT, timecode and EDL: 9 of 10 red

```
baseline FAILED=0
RED    SRT times are NOT rebased to the clip (every subtitle offset by the in-point)
RED    SRT cue start and end are swapped
RED    SRT cue numbering starts at 0
GREEN  the blank line between SRT cues is dropped
RED    timecode frames and seconds are swapped                          (6 tests)
RED    timecode hours and minutes are swapped                           (3 tests)
RED    EDL source range written in CLIP time (conforms the top of the episode)
RED    the EDL audio event is dropped (picture conforms, speech does not)
RED    the EDL declares drop-frame while writing non-drop
RED    a newline in the title is written through, truncating the EDL
```

M3.6's delivery renderers hold. Every mutation that would corrupt a conform was caught by a test that
names the property.

### The one survivor, and why nothing was added for it

Dropping the blank line between cues. The obvious claim â€” "that is malformed SRT, players will fail" â€”
did not survive measurement against the only real parser on this machine:

```
well_formed     cues ffmpeg read: 3   (3 were written)
no_blank_line   cues ffmpeg read: 3   (3 were written)
```

ffmpeg 8.1.1 accepted both and **re-emitted the missing blank lines**, repairing the file. So I looked
for the case where the separator is load-bearing: a cue whose own text is a numeral, where without a
blank line the next cue's index is indistinguishable from a continuation of the previous cue's text.
Â§4.1 has a numeral rule, so a subtitle that is just "2" is ordinary Kurdish content.

```
numeral_with_blank      ffmpeg read 2 cue(s) of 2
numeral_without_blank   ffmpeg read 2 cue(s) of 2
```

Identical output. **No test was written**, because the loop's rule is that a premise you cannot
reproduce is not a finding, and I have no stricter parser here to reproduce it with. Recorded so the
next reader knows this was examined rather than missed.

## Part 2 â€” `editing.json`: one real survivor

```
baseline FAILED=0
RED    the clip's in-point vanishes                    (3 tests)
RED    the clip's out-point vanishes                   (3 tests)
RED    in and out are swapped                          (2 tests)
RED    the transcript section vanishes                 (4 tests)
RED    the QC section vanishes                         (3 tests)
GREEN  every clip claims the verbal path
RED    the speaker attribution vanishes                (3 tests)
RED    the editorial verdict is always written as absent (2 tests)
```

Hardcoding `DiscoveryPath.VERBAL.value` in `Clip.to_dict` left `test_clip.py`, `test_pipeline.py`,
`test_path_a.py`, `test_delivery.py` and `test_boundary.py` **entirely green**.

The reason is the shared fixture: `a_clip()` at `tests/test_clip.py:93` builds a verbal clip, so the
shape test and the round-trip test compared `"verbal"` against `"verbal"`. Correct tests, blind because
the fixture happened to satisfy the rule â€” D-095 and D-098's shape, in a third place.

It matters past the label. Â§8.2's `recall_at_k_by_path` and `path_unique_wins` partition on
`discovery_path in (path, DiscoveryPath.BOTH)`, and `Clip.from_dict` rebuilds the enum from this field,
so a run resumed from a mislabelled artifact carries the wrong attribution into the numbers M2.5's row
says still mean something.

Fixed by parametrizing over every member on both emitting sites â€” `Clip` and `RejectedCandidate`, whose
docstring quotes Â§5: "that set is your only measure of recall" â€” plus a control that three members
render as three **distinct** strings, since a faithful copy of colliding members would satisfy the
parametrized tests and still lose the distinction.

```
baseline FAILED=0
CAUGHT   Clip.to_dict hardcodes verbal (the defect)          FAILED=3
CAUGHT   Clip.to_dict hardcodes both                         FAILED=6
CAUGHT   two enum members render identically (the control)    FAILED=2

3/3
```

Gate: `VERIFY OK â€” 1188 passed, 0 skipped`.
