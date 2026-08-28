# Impact map — pro-edit

## `crop_filter` — `render.py:295` — **crop dimensions become time expressions**

19 call sites in `src/hawedit/render.py`, `tests/test_render.py`, `tests/test_caption_timing.py`,
plus the §4.3.6 golden pixel comparison. New behaviour is opt-in through a new argument so every
existing caller keeps its exact filter string; the golden path is the non-regression test.

| caller | site | covered by |
|---|---|---|
| `render_clip` | `render.py` | `tests/test_render.py` filter-chain suite, golden render |

## `chunk_caption_events` — `captions.py:585` — **gains emphasis and a time shift**

| caller | site | covered by |
|---|---|---|
| `pipeline` Stage 6 | `pipeline.py` | `tests/test_caption_timing.py`, `tests/test_captions.py` |

Emphasis is a style override inside an existing event; the event's text must be byte-identical
(AC-6), which is what stops it becoming a transcript edit and breaking invariant #1.

## `Clip.output` — `clip.py` — **records the removed silence and the edit shape**

`Output` is serialized into the delivered `.json`; new fields are optional so every artifact
written before this still deserializes, as D-033 established.

## `dead_air_flags` — `pipeline.py` — **stops being advisory**

Today it flags internal silence and nothing acts on it. T4 makes it the input to tightening, so
the flag and the cut cannot disagree about where a pause is.

## Gap found

No test asserts anything about the *visual variety* of a render: not a cut count, not a scale
change, not a shot duration. A 34-second single-framing clip passed every check in the suite,
which is why nobody noticed it was not an edit.
