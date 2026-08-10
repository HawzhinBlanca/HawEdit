# Adversarial pass #21 — M3.6's delivery set

> Measured 2026-08-10 on hawapc01 against `57c9a76`.

M3.6 is **DONE** for *"§2's delivery set complete: SRT and EDL alongside the MP4, ASS and §5 JSON"*.
Nineteen mutations, one per claim the cell makes.

## Every stated claim held

```
RED  SRT cues carry source-absolute times instead of the clip's
RED  the SRT time separator becomes WebVTT's period
RED  the SRT stops wrapping and ships one line per sentence (D-114's defect)
RED  the SRT wraps at a different width from the ASS
RED  an incomplete sentence is shipped in the SRT (invariant #2)
RED  a sentence starting before the clip is shipped anyway
RED  a sentence running past the clip's end is shipped anyway
RED  an empty SRT is written rather than refused
RED  the EDL's source timecodes are written in clip time (conforms the wrong footage)
RED  the EDL's record timecodes start at the source's in-point instead of zero
RED  29.97 fps is rounded to 30 and written as non-drop
RED  build_edl uses the rounded rate without validating it first
RED  a non-positive frame rate is accepted
RED  the EDL emits video only, dropping the Kurdish audio it exists for
RED  a clip shorter than one frame produces a well-formed EDL that cuts nothing
RED  a zero-length clip is accepted
RED  a negative clip in-point is accepted
RED  a newline in the title is left in, truncating the EDL for most parsers
RED  the EDL is built after the other two are written, so a refusal ships four fifths
```

So the pass went after what the claims do not say.

## What the claims did not cover

```
ms_to_srt_time(       -1) = '-1:59:59,999'
ms_to_srt_time(     -500) = '-1:59:59,500'
ms_to_srt_time(-3600000) = '-1:00:00,000'
ms_to_timecode(     -500, 25) = '-1:59:59:13'
ms_to_timecode(-3600000, 25) = '-1:00:00:00'

__all__: ['DeliveryError', 'build_edl', 'build_srt', 'ms_to_srt_time', 'ms_to_timecode',
          'parse_srt_times']
```

`divmod` carries the sign into the **minutes**, so the result is not obviously broken — it reads as a
time nearly two hours before the file starts. Both formatters are exported. Refused now; zero still
formats, which is the control.

And the module's own reader:

```
a cue built from a negative start:
'1\n-1:59:59,500 --> 00:00:01,000\nhello\n'
parse_srt_times sees: ()
```

**One cue in, zero out.** `test_pipeline` reads the delivered SRT through this and asserts only that
*some* cue parsed and that the parsed ones lie inside the clip — both satisfied by a dropped cue —
and nothing compared the count to the sentence count.

## The new guard masked an older one

Adding the negative refusal turned one of the nineteen from RED to SURVIVED:

```
SURVIVED  a sentence starting before the clip is shipped anyway
```

`test_a_sentence_before_the_clip_is_refused` matched on `"before"`; the new guard says *"reads as a
time before the file starts"*. With the specific guard deleted the negative offset tripped the new
one and the test still passed. The match now names `"starts before the clip does"`.

## My own control did not discriminate

```
SURVIVED  D-138: the reader scans every line, so an arrow in caption text becomes a timing line
```

Reading the timing as "the first line in the block containing `-->`" is *identical* on a valid cue,
because that line **is** line 1. The two readings diverge only when line 1 is malformed, where
hunting parses a caption line as the timing and invents a cue. That case is the control now.

## Proof

```
baseline green: True
… 23 mutations …
23/23
restored and green: True
```

After **17/18** (the masking) and **22/23** (the weak control).

## On the real artifacts

```
m27e/fixture-s0-1.srt: 2 cues parsed, 2 timing lines in the file -> match True
   100..1700 ms  (both >= 0: True)
   2000..4100 ms  (both >= 0: True)
m27f/whole-s0-1.srt: 2 cues parsed, 2 timing lines in the file -> match True
```

The strict reader refuses nothing this system writes.

Gate: `VERIFY OK — hawedit gate green`, 1379 tests.
