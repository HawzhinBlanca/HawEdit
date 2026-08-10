# Adversarial pass 26 - malformed SRT cues cannot disappear

Date: 2026-08-10
Baseline: `e175dd126ef0692d6726b4bb7c56810d9cdf80f4`

## Finding

The readiness branch already refused negative SMPTE timecode but its other exported formatter did
not. `ms_to_srt_time(-1)` emitted `-1:59:59,999` and `ms_to_srt_time(-500)` emitted
`-1:59:59,500`: Python carried the sign through `divmod`, producing plausible-looking timestamps
nearly two hours before the file. Boolean input became one millisecond; fractional and string input
escaped as raw Python errors.

The SRT reader was weaker still. It searched the entire document with one regex, so a malformed cue
was silently absent from the returned tuple. If the timing line was `BAD` but a caption line looked
like a timestamp, that caption became the cue's time. It also accepted minute/second fields of 99,
an end before its start, and missing or reordered cue indices. A pipeline checking only the parsed
cues could therefore certify fewer cues than the file contained.

## Fix and proof

Both public timecode formatters now require an exact non-negative integer millisecond value; boolean,
fractional, string, negative and out-of-range numeric inputs become bounded `DeliveryError`s. Frame
rate validation similarly rejects booleans, strings, non-finite values and integers too large to
represent as a float.

`parse_srt_times` now parses each nonempty cue block by SRT grammar position. It requires one-based
sequential indices, a readable second-line timing field, valid minute/second ranges and `end >
start`. It never scans caption text for a replacement timing line. Hours remain unbounded, matching
the writer, so a 100-hour cue round-trips instead of being rejected by a two-digit regex.

The discriminating tests reproduce every former output and then prove the opposite controls:

- zero still formats and an empty SRT still reads as no cues;
- arrows in caption text remain ordinary text;
- a valid two-cue file returns exactly two cues, including a 100-hour timestamp;
- malformed, reversed, zero-duration, out-of-range, missing and nonsequential timing structures all
  refuse; Windows line endings and spaced blank separators remain valid; and
- the delivery, pipeline, clip and render adjacency suite remains green.

This parser validates the SRT structure HawEdit writes. It is not a permissive repair tool for
arbitrary third-party subtitle dialects; refusing ambiguity is deliberate at the delivery boundary.
