# A word that was not one line, and the caption that lost it

`Word` validated its surface form as *"a non-empty string"* and nothing else. Both formats §2
delivers subtitles in are **line-structured**: an ASS `Dialogue:` event is one line, and an SRT
cue block ends at a blank one. A break inside a surface form therefore does not wrap the
caption — it ends it.

## Reachable, and not through the models

The canonical ASR path cannot produce one. `OmniAsrBackend._align` builds every surface with
`text.split()`, so a hypothesis carrying a break becomes two surfaces:

```
text.split() of a newline-carrying hypothesis -> ['a', 'b']
```

The door is `Word(**w)` — seven construction sites, two of them reading JSON off disk, and one
of those is behind the documented `python -m hawedit.pipeline VIDEO.mp4 --transcript FILE`:

```
== RawTranscript.from_json — the door `--transcript FILE` opens ==
  ACCEPTED: words[1].w = 'a\nدووەم'
```

Nothing upstream objects once the file is internally consistent. Invariant #5's aligner check
passes on `ctc_viterbi`; the aligned-words-appear-in-`text_ckb` cross-check passes as soon as
`text_ckb` contains the same surface — which a file written by a tool that wrapped its own
output would have. `clip.py` has the same door for §5 contracts.

## What it costs, in pixels

Real ffmpeg 8.1.1-full_build (gyan.dev) on hawapc01, real libass, 1080×1920, the shipped Noto
Naskh Arabic. Three renders of the same two-word sentence — the file with the break, the same
file **truncated at the break**, and the intact one:

```
  broken     6,220,800 bytes  sha256 b01fd8a7473cf06676f140700a2c97de798e66ab26978e963406c9b4c664d7a2
  truncated  6,220,800 bytes  sha256 b01fd8a7473cf06676f140700a2c97de798e66ab26978e963406c9b4c664d7a2
  intact     6,220,800 bytes  sha256 41770c2fe65c568140624b9b5586a3877862f43f1a2f422346550c22d89b4719

broken == truncated (the tail never rendered): True
broken == intact    (the tail did render)    : False
pixels differing between broken and intact  : 8,277
```

The broken render is **byte-identical** to the one with the tail deleted. `دووەم` never reached
the pixels. The intact comparison is what stops that identity being vacuous: the word is drawn,
8,277 pixel bytes' worth, when it survives to the Dialogue line.

## Both readback checks agreed with the file

```
  Dialogue lines: 1
  lines in [Events] that are not Dialogue/Format: ['دووەم']
  parse_dialogue_times says: ((0, 900),)
  same times from the intact file: ((0, 900),)
  the word 'دووەم' is on the Dialogue line: False
```

The tail is sitting in `[Events]` as a line libass does not recognise and therefore ignores.
`parse_dialogue_times` returns **exactly** the intact file's times.

The SRT half is the same defect in the other format:

```
  |1
  |00:00:00,000 --> 00:00:00,900
  |یەکەم a
  |
  |دووەم
  |
  parse_srt_times says 1 cue(s): ((0, 900),)
  blocks a player reads: 2
  block 1 text lines: ['یەکەم a']
```

One cue reported, two blocks in the file, and the tail orphaned with no timing. D-138 made
`parse_srt_times` refuse an unreadable *timing* line; nothing looks at the text, so the cue
count is not a check that the text survived.

## The guard

One check in `Word.__post_init__` — the chokepoint every construction site routes through,
including both JSON readbacks:

```python
if self.w.splitlines() != [self.w]:
```

`splitlines()` rather than a hand-picked character list, so the definition of "a line break" is
the standard library's and not mine. `!= [self.w]` rather than `len(...) == 1`, because the
latter accepts a **trailing** break — `"a\n".splitlines() == ["a"]` — which is just as fatal
once `" ".join` puts the next word after it.

## Mutation audit — 3/3, lint-clean, against a baseline verified green first

Whole suite per mutation, so collateral is visible; lint run with the exact command `verify.sh`
uses, because a mutation that only breaks ruff measures ruff (D-148, D-150).

```
baseline (must be green before any mutation is trusted):
  lint clean: True   pytest exit: 0   failures: []

CAUGHT    the defect restored: no requirement that a surface form be one line
           red (13):
             tests/test_transcripts.py::test_a_supplied_transcript_carrying_a_broken_word_is_refused_at_the_door
             tests/test_transcripts.py::test_a_surface_form_that_is_not_one_line_is_refused[\nb]
             tests/test_transcripts.py::test_a_surface_form_that_is_not_one_line_is_refused[a\n\nb]
             tests/test_transcripts.py::test_a_surface_form_that_is_not_one_line_is_refused[a\n]
             ... 12 parametrised breaks and the --transcript door, nothing else

CAUGHT    the length spelling, which accepts a trailing break
           red (1):
             tests/test_transcripts.py::test_a_surface_form_that_is_not_one_line_is_refused[a\n]

CAUGHT    over-broad: any whitespace at all is refused
           red (4):
             tests/test_transcripts.py::test_whitespace_that_does_not_break_a_line_is_still_accepted[…]
             (all four cases, and nothing outside that test)

file restored byte-identical: True
3/3 caught lint-clean
```

The second and third are the ones that measure the **threshold** rather than the guard's
existence. `len(splitlines()) != 1` reddens exactly one case — the trailing break — so the
choice of spelling is pinned by a test and not by the comment beside it. Refusing all
whitespace reddens exactly the four accepted cases and nothing else, so the control is
load-bearing in both directions.

**Not counted, and why.** The pixel test and the SRT structural test redden under no mutation
of the guard, because they do not test the guard: they pin the **premise** it rests on — that
a break inside a caption line costs the text after it. Calling them controls would repeat the
isolated-mutation mistake this loop keeps finding (D-149, D-155…D-162, D-166). Their value is
that their cheapest fix is a re-measurement: if a future libass ever starts rendering the
orphaned line, `broken == truncated` fails and D-167's threshold is reopened with evidence.

**Not fixed, and named:** a surface form may still contain an ordinary space or tab, so one
`Word` can cover two spoken words with a single timing. That degrades `WORD_HIGHLIGHT` karaoke
rather than losing text, and no measurement here demonstrates it, so it is recorded instead of
guessed at.
