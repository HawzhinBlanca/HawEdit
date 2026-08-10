# The SRT sidecar shipped cues no player can read in order

`build_srt` refused an incomplete sentence (invariant #2), one starting before the clip, and one
ending after it. Every one of those is a check about a sentence **on its own**. Nothing checked
the sequence — and SRT is read sequentially.

## Measured, before the guard

Driving the real `build_srt` and reading back the emitted file with `parse_srt_times`:

```
=== cues out of order — the later sentence first ===
    SHIPPED. cues=((1000, 1400), (0, 400))
    non-overlapping and ascending: False   every cue positive-length: True
    1
    00:00:01,000 --> 00:00:01,400
    باشە

    2
    00:00:00,000 --> 00:00:00,400
    ئەمە

=== cues overlapping — the second starts before the first ends ===
    SHIPPED. cues=((0, 1200), (800, 1400))
    non-overlapping and ascending: False

=== a sentence whose words are unordered, so the cue runs backwards ===
    SHIPPED. cues=((900, 400),)
    every cue positive-length: False
    1
    00:00:00,900 --> 00:00:00,400
    باشە ئەمە
```

The third is the sharpest: **`00:00:00,900 --> 00:00:00,400`**, a cue whose end precedes its
start, assembled entirely from words that are individually valid. `ms_to_srt_time`'s own docstring
warns about a "plausible-looking timestamp" for negative input (D-138) — this one needs no
negative number at all.

## Why `Word`'s invariant does not cover it

`Word.__post_init__` refuses `end_ms <= start_ms`, so no single word runs backwards, and a
zero-length cue is unreachable:

```
ValueError: word end_ms must be after start_ms
```

But `Sentence.start_ms` is `words[0].start_ms` and `end_ms` is `words[-1].end_ms`, with nothing
requiring the tuple to be sorted — and nothing at all constrains two sentences relative to each
other. Never computed, not computed and discarded.

## Reachability, stated honestly

`segment_sentences` emits sentences in order from ordered words, so the pipeline does not produce
these today. `build_srt` and `build_ass` are both exported in `__all__` and both take any
`Sequence[Sentence]`, and `pipeline.py` hands **the same sequence** to both — so a guard on one
and not the other would burn an overlap into the video while the sidecar refused it. The guard is
one function called by both, not a check per writer.

## The rule, and where it stops

`assert_deliverable_order` refuses a sentence that ends at or before it starts, and a pair where
`later.start_ms < earlier.end_ms`. **Touching exactly is allowed** — `later.start_ms ==
earlier.end_ms` is ordinary consecutive speech, and refusing it would reject honest output. That
boundary is the control in two of the tests.

**Rejected: sorting the sentences instead of refusing them.** A writer that quietly reorders its
input turns a producer bug into a silent correction, and the next reader has no way to know the
sequence it was handed was wrong. §4.3's warning is about failures that "do not appear and nothing
says so"; sorting is one.

**Rejected: putting the check in `Sentence.__post_init__`.** A `Sentence` with unordered words is
a legitimate intermediate for code that has not sorted yet; the property that matters is at the
point of *delivery*, which is where the guard lives.

## Mutation audit — 6/6

```
baseline green: True
CAUGHT    the backwards-sentence half of the check is dropped
           red: test_a_sentence_whose_words_are_unordered_is_refused
CAUGHT    the overlap half of the check is dropped
           red: test_cues_that_go_backwards…, test_overlapping_cues…,
                test_the_burned_in_captions_refuse_the_same_sequence_the_sidecar_does
CAUGHT    the sidecar writer stops calling it
CAUGHT    the burn-in writer stops calling it
CAUGHT    the rule refuses cues that merely touch (over-strict), control intact
CAUGHT    the rule refuses touching cues AND the control that catches it is dropped
6/6
```

The two halves of the check are mutated separately, so neither is carried by the other. The two
call sites are mutated separately too, which is what proves the burn-in and the sidecar are both
covered rather than one standing in for both.

**Two of these were re-run because the first pass was contaminated.** Removing
`assert_deliverable_order(sentences)` orphans its import, so ruff reddened the
gate-as-subprocess tests and the catch partly measured ruff (D-148, D-150). Redone with the
import removed alongside the call:

```
CAUGHT    the sidecar writer stops calling it  lint_clean=True
           red (3): test_a_sentence_whose_words_are_unordered_is_refused,
                    test_cues_that_go_backwards_are_refused_rather_than_written,
                    test_overlapping_cues_are_refused_rather_than_written
CAUGHT    the burn-in writer stops calling it  lint_clean=True
           red (1): test_the_burned_in_captions_refuse_the_same_sequence_the_sidecar_does
```

Each is caught by exactly the tests written for it, and nothing else.

**The over-strictness pair follows D-162's rule** — the control is mutated together with the state
it describes. Making the rule reject touching cues reddens four unrelated tests that build
consecutive sentences, which is the honest signal that over-strictness breaks ordinary output;
removing the dedicated control as well does not rescue it.
