# Adversarial pass on Kurdish invariant #4 — six claims held, one was a string

> Measured 2026-08-08 on hawapc01, ffmpeg 8.1.1-full (libass + HarfBuzz + FriBidi on `PATH`).

Iteration 10's adversarial pass. Target: the row that claims invariant #4 is **"fully enforced.
Shaping, stack check on a real build, font coverage on the real font, our own line breaks, and a
golden render compared per gate run with `shaping=simple` as a failing negative control."**
Chosen because it is the one that puts broken Kurdish in front of a client if it is false, and
because it had never been audited.

## What survived

**1. The committed reference reproduces pixel-exact on this build.** Not "close" — a fresh render
decoded to RGB24 is byte-identical to `tests/golden/kurdish-caption.png`, 6 220 800 bytes.

**2. The reference contains real shaped text, not a blank or a row of tofu.** A golden test can
pass by comparing nothing to nothing, so the pixels were counted rather than trusted:

```
golden: 2734 ink px, one band at rows 1731-1771, 16 column runs, widest run 35 px
```

One band of 41 rows is one 64 px caption line, at the bottom of a 1080x1920 frame. Read directly,
the line is `ڕۆژنامەوانی کوردی لە هەولێر.` with the sentence-final period at the **left** — where
an RTL run ends.

**3. `shaping=simple` genuinely differs, and the comparison is exact.**

```
complex vs simple: 4803 of 2073600 px differ (0.232%)
ink 2734 vs 2767 (ratio 0.988), column runs 16 vs 19
```

Note how small that is. The two renders have almost the same amount of ink and differ in three
column runs — because `simple` breaks the *joining forms* rather than the letter count. A
tolerance-based comparison would have to be tuned below 0.232% to catch it; `compare_golden_render`
uses exact equality on decoded pixels, so it cannot be fooled by a subtler shaping failure.

**4. Six of six mutations caught.** Each guard reverted in turn, the whole suite run, the file
restored, against a baseline verified green first:

```
CAUGHT  §4.3.1's prohibition: production emits shaping=complex, never auto
CAUGHT  the golden render's own shaping default
CAUGHT  the golden pixel comparison itself
CAUGHT  refusing a missing golden reference
CAUGHT  the HarfBuzz/FriBidi stack check
CAUGHT  the Kurdish font-coverage check
```

**5. "In CI" is true.** `.github/workflows/gate.yml` fetches the pinned ffmpeg and then runs a
dedicated step that greps the golden test's output for `skipped` and exits non-zero if it finds
it — so a failed fetch cannot silently retire the invariant. (It is still not a *required* status
check; that is `BLOCKED.md` #7, already recorded.)

**6. `WrapStyle: 2` is load-bearing, which nothing had shown.** Twelve Sorani words on one line,
960 px of play area:

| Header | Rendered |
|---|---|
| `WrapStyle: 2` | **1 band**, x-span 0..1079 — kept on one line, clipped at the frame |
| `WrapStyle: 0` | **3 bands**, x-span 262..818 — libass broke it where it chose |
| `WrapStyle: 1` | 3 bands, x-span 92..988 |

## What did not survive

**"Our own line breaks" was asserted three ways and rendered zero times.**

- `wrap_caption_lines` is unit-tested on tuples of words.
- `build_ass` is asserted to contain `\N`.
- The header is asserted to contain the string `WrapStyle: 2`.

None of those is a pixel. And the golden reference **cannot** supply one:
`GOLDEN_CAPTION_TEXT` is 28 characters against a 32-character limit, so it is a single line. The
one claim in invariant #4 that involves layout was the one claim never rendered.

Measured on a 50-character Sorani sentence, which is what the claim is about:

```
with our \N      2 ink bands, rows 1667-1707 and 1728-1765
with \N removed  1 ink band,  rows 1728-1771
```

Three tests now close it — the two-band assertion, the one-band negative control that makes the
first mean something, and a rendered demonstration that `WrapStyle: 2` changes the band count.
Both mutations caught: dropping `\N` from `build_ass`, and `WrapStyle: 2` -> `0`.

**A pixel test cannot catch the `WrapStyle` mutation on production output, and that is worth
stating rather than papering over.** With our own `\N` present, `WrapStyle: 0` renders
**byte-identical** to `WrapStyle: 2` — 0 pixels differ. The setting only matters for a line wider
than the play area, and our 32-character limit means production never emits one. So the string
assertion is the right instrument for that particular claim, and the new test demonstrates the
behaviour on deliberately over-wide input instead.

## Checked, and not a defect — recorded so it is not raised again

`WrapStyle: 2` means an over-wide line is **clipped at the frame edges rather than wrapped**, and
`wrap_caption_lines` deliberately does not split a word longer than `max_chars` because splitting
Arabic-script mid-word breaks shaping. That looked like a live path to clipped Kurdish, so the
threshold was measured rather than argued — a single unbreakable word, growing:

| Chars | Rendered width | |
|---|---|---|
| 25 | 355 px | |
| 32 | 477 px | the default limit |
| 40 | 586 px | |
| 50 | 715 px | still inside the 960 px play area |

About 14.3 px per character, so a single word needs roughly **67 characters** to reach the play
area's edge. Real agglutinated Sorani forms — `بەرپرسیارێتییەکانیشیانەوە` is 25 — do not approach
that. The 32-character limit carries better than a 2x margin, so no guard was added: this is a
case that cannot occur with Kurdish, and writing a check for it would be inventing work. The
75-character string that first produced clipping in this audit was `stem * 3`, not a word.

## The correction to the record

The invariant table's "fully enforced" was true of shaping, the stack check, the font and the
golden comparison, and was **not** true of line breaks, which had no rendered evidence at all.
That phrase covered five claims and four of them were tested. D-061.
