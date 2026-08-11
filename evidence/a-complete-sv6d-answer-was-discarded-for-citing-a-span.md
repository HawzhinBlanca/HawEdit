# A complete, correct SV6D answer was discarded for citing a span

The second half of D-118. That entry found this exact message on the real 38-minute run —

```
✗ the model returned no usable line for ['subject', 'aesthetics', 'camera', 'editing',
  'narrative', 'retention']
```

— and fixed its **blast radius**: one unreadable window no longer discards every other candidate.
It treated the refusal itself as correct. It was not. The model had answered, completely and
correctly, and the answer was thrown away in silence.

## The measurement

From `path_b_result.json`, the one window of seven that came back `unreadable` on the real run:

```
window : ZAR38MinTest:s54:w4
bounds : 1040.287s .. 1043.818s   (3.531 s)
reason : PathBError: the model returned no usable line for ['subject', … all six …]

subject    | 0.0-3.5 | Two men in a studio setting, one speaking and gesturing, the other listening attentively
aesthetics | 0.0-3.5 | Bright, modern studio with blue and yellow walls, plants, and a colorful table runner
camera     | 0.0-3.5 | Wide shot capturing both men and the table, static with no movement
editing    | 0.0-3.5 | No cuts or transitions, smooth and continuous
narrative  | 0.0-3.5 | A conversation or interview taking place, with one man speaking and the other listening
retention  | 0.0-3.5 | The engaging conversation and modern aesthetic would keep viewers watching
```

Six lines, six dimensions, each naming a real one, each with a description, each citing a time.
The description is also **right** — frames decoded at 1157 s and 1271 s of this file show exactly
that: two men across a table with microphones in a studio.

**Computed and discarded, not never computed.** `_LINE` required the second field to be a bare
number:

```python
r"^\s*(?P<name>[a-z]+)\s*\|\s*(?P<at>[0-9]+(?:\.[0-9]+)?)\s*\|\s*(?P<text>.+?)\s*$"
```

Against `0.0-3.5` the `at` group matches `0.0`, the next character is `-` rather than `|`, and the
whole line fails. `parse_sv6d_lines` then did `if match is None: continue` — so all six were
dropped as noise and reported as six dimensions the model never returned.

Verified directly before changing anything:

```
_LINE.match('subject | 0.0-3.5 | …')  -> None
_LINE.match('subject | 0.0 | …')      -> matched
```

## The root defect is the silence, not the span

Supporting `0.0-3.5` alone would fix this line and leave the next unanticipated format to vanish
the same way. So the fix is in two parts, and the second is the important one:

1. **A span is read**, anchored at its start, with **both** ends bounds-checked.
2. **A line naming a real dimension is never skipped.** It parses or it is refused *by name*.
   A line that names no dimension is still left alone — the model's prose, a heading or a
   markdown rule is noise, and that distinction is what keeps the change from turning chatter
   into refusals.

Before, a dimension line this module could not read became "the model returned no usable line",
which sends the operator after a model that answered fine. Now it says which dimension, what it
cited, and that the line was otherwise complete.

## The judgement, and what was rejected

**Anchor a span at its start.** It is a number the model itself wrote. **Rejected: the midpoint**
— nobody observed it; inventing it is the same defect as filling a missing dimension with a
default, which `parse_sv6d_lines` already refuses to do in the very next branch. **Rejected: the
end.** **Rejected: keeping the refusal** on the grounds that `SV6D_PROMPT` asks for a bare number
— the prompt asks, the model answers how it answers, and §3's rule is *"Reject output where a
claim has no timeline evidence."* `0.0-3.5` is timeline evidence; it is more of it than a point,
not less. Refusing it enforces the prompt's formatting, not the blueprint's rule.

**This reverses a position the repo already held**, and it is reversed openly rather than quietly:
`tests/test_video_reader.py` carried `REAL_RANGE_OUTPUT` with the comment that a span means §3
*"refuses all six"*. That fixture is kept and is **still unreadable in that test** — for the
reason it should be, since it cites 3.5 s of a 1.4 s window, which is a moment the model was never
shown. Its comment now says so, and the assertion names the clip length instead of "no usable
line". D-118's guard — one unreadable window does not discard the others — is untouched and still
driven through the real `read_scenes`.

## Proof on the artifact

The real discarded window, re-parsed and shifted onto the media clock:

```
before : discarded — "the model returned no usable line for ['subject', …]"
after  : 6/6 dimensions parsed

  subject   : 1040.287s Two men in a studio setting, one speaking and gesturing, the other listening attentively
  camera    : 1040.287s Wide shot capturing both men and the table, static with no movement
  narrative : 1040.287s A conversation or interview taking place, with one man speaking and the other listening
```

That run returned **6 candidates and 1 unreadable**. This window becomes the 7th.

## Mutation audit — 6/6 lint-clean

```
baseline: GREEN
baseline lint: clean

CAUGHT   a span is not recognised at all, so the real answer is refused again
CAUGHT   the line shape rejects anything but a bare number, so span lines vanish as noise
CAUGHT   a span is anchored at its midpoint — a number no model observed
CAUGHT   only the near end of a span is bounds-checked, so it may leave the clip
CAUGHT   a backwards span is silently accepted instead of refused
CAUGHT   an unreadable dimension line defaults to 0.0 instead of refusing

file restored byte-identical: True
6/6 caught lint-clean
suite after restore: GREEN
```

Two controls carry the change: a plain point still parses exactly as before, and a line naming no
dimension is still left alone — without that second one, "never skip a line" would have been
satisfied by refusing the model's own prose.
