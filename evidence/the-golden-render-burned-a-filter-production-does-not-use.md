# §4.3.6's pixel safeguard rendered a filter string production does not use

D-163 (adversarial pass 26) found that `subtitle_filter` (production) and `render_caption_png`
(the golden render) each built `ass=…:shaping=…:fontsdir=…` independently, and recorded it as
remaining debt: *"a future element added to one and not the other is not [covered]."* This closes
that.

## The two strings, before

Identical character for character, and nothing required them to stay so:

```
production : ass=C\\:/tmp/w/captions.ass:shaping=complex:fontsdir=C\\:/tmp/w/fonts
golden     : ass=C\\:/tmp/w/captions.ass:shaping=complex:fontsdir=C\\:/tmp/w/fonts
identical  : True
```

So §4.3.6 — the safeguard §0 calls failure mode #3, *"you will catch it when a client sees the
burned-in captions"* — was comparing pixels rendered from a copy.

## What the change buys, measured both ways

Same production regression each time: `subtitle_filter` pointing `fontsdir` at the wrong directory
(§4.3.4 exists because fontconfig resolving the font is not the same as shipping it). Only the
pixel tests:

```
AFTER  (coupled, as committed): production's fontsdir broken -> pixel tests green=False  caught it
        red: test_the_render_matches_the_golden_reference
BEFORE (independent copy)     : production's fontsdir broken -> pixel tests green=True   MISSED IT
```

## What it does *not* buy: this was never an uncovered hole

The tempting claim is that the regression would have shipped. It would not. With D-164's own two
tests removed and the coupling reverted, the whole suite still goes red:

```
BEFORE D-164 + production's fontsdir broken, whole suite:
  green=False
  red (1): test_a_windows_path_is_escaped_for_both_unescaping_passes
```

**Exactly one** pre-existing test — a string test that asserts the escaped `fontsdir` path — caught
it. So this change is **defence in depth, not a closed hole**, and it is recorded that way. What it
adds is that the pixel safeguard now sees production's string at all: an element the string tests
do not happen to assert is now rendered and compared, which is the case the string tests cannot be
enumerated against in advance.

## The change

`render_caption_png` derives its filter from `subtitle_filter` instead of spelling it out. The
`shaping` parameter — which exists only so the negative control can render the wrong way — reaches
`simple` by replacing production's `shaping=complex`, and **refuses** if that substring is absent:

```python
filter_string = subtitle_filter(ass_path, fonts_dir)
if shaping != "complex":
    wrong = filter_string.replace("shaping=complex", f"shaping={shaping}", 1)
    if wrong == filter_string:
        raise ValueError(…)
    filter_string = wrong
```

Without that refusal the replacement would silently no-op, `test_simple_shaping_fails_the_golden_test`
would render the **right** way, find it equal to the reference, and fail — reading as a shaping
regression when the truth is a broken test.

## Mutation audit — 5/5

```
baseline green: True
CAUGHT    BEFORE D-164: production's fontsdir breaks and the golden render keeps its own copy
CAUGHT    AFTER: the same production regression, with the render coupled
CAUGHT    the golden render goes back to building its own filter
CAUGHT    it derives the filter and then rebuilds it inline anyway
CAUGHT    the refusal for an unreplaceable shaping is dropped
5/5
```

The fourth is the wiring test's plausible dodge — call `subtitle_filter` and throw the result away
— and it is caught by the `f"ass=` control beside the call, not by the call assertion. The fifth
reaches the new `raise` through a monkeypatched `subtitle_filter`, so the refusal is exercised
rather than merely present.

**One correction to the sweep.** Mutation 1's self-check asserted
`"subtitle_filter(ass_path" not in out`, which is also `subtitle_filter`'s own `def` line, so it
fired on the definition and reported a mutation that had in fact applied. Narrowed to
`"filter_string = subtitle_filter("`.
