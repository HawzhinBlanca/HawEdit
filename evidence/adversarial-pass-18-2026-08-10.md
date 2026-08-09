# Adversarial pass #18 — M3.1's four deliverables

> Measured 2026-08-10 on hawapc01 against `5a064ff`, ffmpeg 8.1.1-full (libass/HarfBuzz/FriBidi).

M3.1 is **DONE** for *"§4.3 caption generation: shaping, stack check, font coverage, own line
breaks"*, and the cell reads, in full:

> `src/hawedit/captions.py` + `tests/test_captions.py`. Font coverage asserted against the real
> OFL-1.1 Noto Naskh Arabic shipped in `assets/fonts` — full Kurdish coverage measured (D-018).

Four deliverables, one of them substantiated. So the pass went after the other three, and then after
the one that was substantiated.

## 1. "full Kurdish coverage" was eleven characters, and two Kurdish letters were not among them

```
KURDISH_REQUIRED_GLYPHS: 11 characters
  ه U+0647  پ U+067E  چ U+0686  ڕ U+0695  ژ U+0698  گ U+06AF
  ڵ U+06B5  ھ U+06BE  ۆ U+06C6  ێ U+06CE  ە U+06D5
```

`normalize_sorani` — §4.1, the module this product normalizes every transcript with:

```
normalize_sorani('كوردي')
  in :  ك=U+0643 و=U+0648 ر=U+0631 د=U+062F ي=U+064A
  out:  ک=U+06A9 و=U+0648 ر=U+0631 د=U+062F ی=U+06CC
```

Its docstring: *"Arabic `ي`/`ك` to the Farsi forms Kurdish uses."* Those forms are `ک` U+06A9 and
`ی` U+06CC. Neither was in the font requirement.

`GOLDEN_CAPTION_TEXT`, this project's own §4.3.6 reference line, is
`ڕۆژنامەوانی کوردی لە هەولێر.` — it uses both. And the comment above it in `captions.py` read
*"plus ڕ ۆ ژ ە ی from §4.3.4's required set"*, naming `ی` as required while the set had no `ی`.

## 2. What that certifies, measured on a real font

The shipped Noto Naskh Arabic, subset to drop **only** U+06A9 — every other glyph, every layout
feature, the family name unchanged, so libass resolves it by the same name the ASS asks for:

```
subset font: U+06A9 present? False   U+0643 (Arabic kaf) present? True   codepoints 1122
assert_font_covers_kurdish: PASSED — a font with no Kurdish kaf is certified
```

The Kurdish keheh is not the Arabic kaf. A font can plausibly have one and not the other, and this
one now does.

## 3. The pixels

```
shipped    21,847 B png   6,220,800 B rgb24   8,367 subpixels above black
no-keheh   22,165 B png   6,220,800 B rgb24   9,267 subpixels above black

pixels differ: True   subpixels changed: 15,999 (0.26% of the frame)
```

§4.3.4 says *"Missing glyphs render as boxes."* Measured, it is worse: libass falls back to another
font for that one character, so `کوردی` comes apart into a detached, differently sized `ک` and
`وردی`. The viewer reads one word as two, and the caption looks entirely present — the frame gains
ink rather than losing it.

**The first attempt at this measurement reported `pixels differ: False`, and it was wrong.** Both
frames were solid black: the reference frame is grabbed at t=0 and the words had been given a 200 ms
start, so nothing was on screen and two empty frames compared equal. Caught by printing the lit
subpixel count beside the verdict; the new test asserts both frames carry >4,000 lit subpixels
before comparing them, so that trap cannot be re-entered silently.

## 4. The check had no caller in the product

```
$ grep -rn "assert_font_covers_kurdish" src/ scripts/
(nothing)
```

Its own docstring says *"this runs at build time rather than being trusted"*. It ran in one test,
against one hard-coded path. `render_clip` takes `fonts_dir` and hands it straight to
`subtitle_filter`, and `pipeline._runtime_fonts_dir()` resolves to `sys.prefix/share/hawedit/…` off
an installed deployment — a directory no test has ever looked inside.

`assert_fonts_dir_covers_kurdish(fonts_dir)` now runs in `render_clip`, beside `assert_rtl_stack`,
for the reason that call already gives: *"Checked here, not only in the golden test."*

## 5. The mutation audit, and the two survivors

```
baseline green: True

RED  D-133: the Kurdish keheh and yeh drop out of the required set again (the defect)
RED  D-133: the burn stops verifying the font directory it was handed
RED  D-133: an empty fonts directory is accepted instead of refused
RED  D-133: any font in the directory counts, covering or not
RED  M3.1 shaping: the filter falls back to libass's default shaping
RED  M3.1 stack check: --disable-libass no longer beats --enable-
RED  M3.1 stack check: the burn stops verifying the RTL stack
RED  M3.1 font coverage: a missing glyph is reported as covered
RED  M3.1 own line breaks: libass wraps the text instead of us
RED  M3.1 own line breaks: the computed break is not emitted
RED  M3.1 own line breaks: everything goes on one line

11/11
restored and green: True
```

**The first pass was 9/11.** Both survivors were on the *stack check* — the one deliverable of the
four that is genuinely wired into production:

* the `disabled` precedence in `assert_rtl_stack.find()` could be deleted with 1,332 tests green,
  because every other refusal reaches `None` by absence and only a buildconf carrying **both**
  `--enable-libass` and `--disable-libass` can tell the difference;
* `assert_rtl_stack(buildconf, linked_libraries(binary))` could be deleted from `render_clip` and
  nothing noticed — the same unheld-wiring shape as the font check having no caller at all
  (D-105, D-108).

Both now have tests, the first with a control requiring the identical configure line minus the
`--disable-` to be **accepted**, so it measures the precedence and not merely that some string is
refused.

## What survived

**Shaping (§4.3.1/§4.3.3) and our own line breaks (§4.3.5) held completely** — three mutations each,
all caught, several by the pixel-level band-counting tests the 2026-08-08 pass added. §4.3.6's golden
comparison held too: `shaping=simple` still fails it. Nothing in those four requirements was found
wanting.

Gate: `VERIFY OK — hawedit gate green`, 1337 tests.
