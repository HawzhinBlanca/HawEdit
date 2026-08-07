# Evidence — §4.3 RTL shaping, measured on a real render

**Task:** M3.2 · **Date:** 2026-08-06 · **Reproduce:**
`bash scripts/fetch-ffmpeg.sh && bash scripts/verify.sh`

§0 names this failure mode #3: "FFmpeg's default shaping engine breaks Arabic-script text.
You will not catch it in code review — you will catch it when a client sees the burned-in
captions." This is that claim, rendered.

## Build

```
ffmpeg version n8.0.1-48-g0592be14ff  (--enable-gpl --enable-version3)
  --enable-libass  --enable-libharfbuzz  --enable-libfribidi
```

`assert_rtl_stack()` passes on this build's real `-buildconf`, reporting
`harfbuzz_source='buildconf'`.

The build's own help confirms what §4.3 documents:

```
shaping  <int>  set shaping engine (from -1 to 1) (default auto)
  auto     -1
  simple    0    simple shaping
  complex   1    complex shaping
```

## The render

Caption text (`GOLDEN_CAPTION_TEXT`), chosen to exercise the joining behaviour plus §4.3.4's
required glyphs:

> ڕۆژنامەوانی کوردی لە هەولێر.

Rendered at 1080×1920 onto black, three ways:

| shaping | SHA-256 (first 16) | Result |
|---|---|---|
| `complex` | `e3d3f3e5d22df202` | correct joining |
| `simple` | `edbc14e2b3d6cf06` | **broken joining** |
| `auto` | *identical to complex* | correct — **on this build** |

`shaping-complex-vs-simple.png` shows the two stacked (complex above, simple below). The
visible breakage is in `لە` and the initial `هـ` of `هەولێر`: `simple` renders isolated
letterforms where Arabic script requires connected ones.

## The finding that matters

**`auto` produced pixels identical to `complex` here.** That is not reassuring — it is the
precise reason §4.3.1 says "Set `shaping=complex` explicitly. Never rely on `auto`."

On a build *with* HarfBuzz, `auto` resolves to complex and everything looks right. A
developer testing on such a build sees correct Kurdish, concludes `auto` is fine, and ships
code that renders broken captions the moment it runs on a host whose libass lacks HarfBuzz.
The bug is invisible exactly where it would be caught.

So the explicit setting is not redundancy. It is the difference between correctness that
happens to hold and correctness that is stated.

## What this closes

Kurdish invariant #4 is now enforced end to end:

- `shaping=complex` emitted explicitly, asserted in `subtitle_filter`
- libass + HarfBuzz + FriBidi verified from the real build config
- font coverage verified against the real shipped OFL font
- our own line breaks, `WrapStyle: 2`
- **golden render compared per gate run**, with `shaping=simple` as a negative control that
  must fail — without it the golden test would be measuring nothing

The comparison runs on decoded RGB pixels, not file bytes, so a PNG-encoder change cannot
fail a render that looks identical. A golden test that cries wolf gets disabled, and a
disabled golden test is how the shaping regression ships.
