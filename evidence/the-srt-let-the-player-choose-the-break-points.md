# The SRT let the player choose the break points

> Measured 2026-08-09 on hawapc01, on `ZAR38MinTest.mp4` — the real 38-minute Sorani file, run
> through the real OmniASR LLM-7B + CTC-3B/Viterbi, not a fixture and not a stand-in transcript.

§2's architecture diagram ends with what leaves the system: `MP4 · SRT/ASS · editing JSON · EDL`.
§4.3 is titled **RTL caption rendering — MANDATORY**, and its fifth requirement is:

> Insert line breaks yourself from the word alignment. … Automatic wrapping on RTL text produces bad
> break points regardless.

`build_ass` does that — `wrap_caption_lines` over the word timings, emitted as `\N`, with
`WrapStyle: 2` disabling libass's own wrapper. `build_srt` wrote `sentence.text`, and `Sentence.text`
is `" ".join(word.w for word in self.words)`. One line, however long the sentence.

## The same sentence through both formats, before the fix

```
max chars per line (DEFAULT_MAX_CHARS_PER_LINE) = 32
sentence: 12 words, 74 chars

ASS  -> 3 lines            29 / 30 / 13 chars,  Dialogue carries our own break
SRT  -> 1 line             74 chars
```

## On the real 38-minute run

```
ZAR38MinTest.transcript.raw.json   878,195 bytes, 6,104 words, 185 complete sentences
sentences <= 60 s, so a clip can carry them   182
  wider than DEFAULT_MAX_CHARS_PER_LINE (32)  149   (81.9%)
  median width                                104 chars  -> 4 lines
  widest                                      973 chars  -> 33 lines
before the fix, every one of those was a single SRT line

longest sentence by time  102.5 s, 1,702 chars, 57 lines
  §4.2 never split it — unpunctuated ASR output, and the VAD-pause branch is dead
  (BLOCKED #14). `build_srt` refuses it for any clip shorter than 102.5 s, so it does
  not reach a sidecar; it is evidence about segmentation, not about wrapping.
```

## What was changed

`build_srt` calls the same `wrap_caption_lines` at the same width and joins the lines with `\n`,
SRT's own in-cue break. A `max_chars_per_line` parameter is exposed the way `build_ass` exposes it.

## Proof

Two controls, because the width assertion alone is satisfied by wrong answers:

- **a sentence that fits stays on one line** — breaking every cue passes the width test and puts a
  break where the speech has none;
- **the reassembled cue equals the sentence exactly** — a wrapper that meets the width by dropping a
  word, or by cutting one in half (which also breaks Arabic shaping), passes the width test too.

And the artifact is read back by something that is not us: ffmpeg demuxes the written file into two
cues of three lines each with every word present.

**That witness is narrower than it first appeared.** Measured, ffmpeg does *not* enforce the
format's rule that a blank line ends a cue — separating the wrapped lines by a blank line
round-trips **byte-identical** to the correct file:

```
our newline                  ffmpeg exit 0, cues ['1', '2'], words missing 0
a blank line (the mutation)  ffmpeg exit 0, cues ['1', '2'], words missing 0
```

So the blank-line hazard is a check about the strict parsers ffmpeg is not, and it is pinned by the
cue-splitting test rather than by the round trip. Both docstrings say which is which, because a
control that agrees for the wrong reason reads as protection it does not have (D-082).

```
baseline fails: False

RED  the cue is one line again (the defect)
RED  every word gets its own line                <- the control
RED  the wrapper loses the last line
RED  lines are separated by a blank line
RED  the break is by character, not by word
RED  the two formats use different widths

6/6
```

Gate: `VERIFY OK — 1237 passed, 0 skipped`.
