# The caption guard's logic was tested; only ruff noticed when its wiring was cut

> Measured 2026-08-09 on hawapc01 against `f3818d2`, against a green 1,136 baseline.

`assert_captions_within_clip` refuses an ASS with nothing to draw inside `[0, clip_duration_ms]` —
subtitles are burned into a stream ffmpeg has already cut, so `t=0` is the start of the clip, and a
file carrying source-absolute stamps draws nothing and ships a caption-free MP4. Kurdish invariant
#4.

The function is well tested: `tests/test_caption_timing.py` covers no-Dialogue, non-intersecting,
partial-overlap and header-only files. **Its call in `render_clip` was not.**

## Two mutations, and only one of them is honest

```
baseline: GREEN
CAUGHT    A: call deleted                     ruff=FAILS  tests_failed=3
SURVIVED  B: guard fed a synthetic valid ASS  ruff=clean  tests_failed=0
```

**A is not a catch.** Deleting the call leaves `assert_captions_within_clip` imported and unused, so
`ruff` reports it and the three `test_gate.py` nested-gate tests fail *because `verify.sh` runs a red
lint*. A linter noticed an unused name. No test observed that captions stopped being checked.

**B is what a careless refactor looks like.** Keep the import used, hand the guard a synthetic
always-valid ASS instead of the file on disk. `ruff` is clean, the guard runs, it checks nothing
real, and the full suite reports **0 failures**. Under B an ASS with source-absolute stamps ships a
valid, playable, caption-free MP4 with `captions_burned_in=True`.

That asymmetry is the finding: the only thing standing between the burn and an unchecked caption file
was an import-usage rule.

## The fix asserts the wiring, through the render path

`test_the_burn_refuses_an_ass_whose_stamps_fall_outside_the_clip` writes an ASS stamped a minute into
the episode — entirely outside a clip that ends well before 60 s, asserted in the test so the fixture
cannot drift into overlapping — and requires `render_clip` to raise `CaptionsOutsideClip`. It also
asserts no MP4 was written, because "refused" and "refused after writing the file" are different
facts.

**The control**: the ordinary ASS this suite builds must still render and still report
`captions_burned_in`. Without it the test would pass for a `render_clip` that rejected every caption
file it was handed.

```
CAUGHT    A: call deleted                     ruff=FAILS  tests_failed=4
CAUGHT    B: guard fed a synthetic valid ASS  ruff=clean  tests_failed=1
```

B now fails exactly one test — mine — with ruff clean, so it is a behaviour catch rather than a lint
trip.

## A note on my own tooling, since it made the same mistake

My first attempt at mutation B was written inline through shell escaping and produced `Found 15
errors` from ruff — the mutation was malformed, so it would have "been caught" for a reason unrelated
to captions. That is D-082's lesson recurring inside the instrument rather than the subject: a
mutation caught for the wrong reason reads as protection that is not there. Rewritten as a file-based
script with the ASS as a short constant so ruff and the formatter stay quiet and the only variable is
the guard.

Gate: `VERIFY OK — 1137 passed, 0 skipped`.
