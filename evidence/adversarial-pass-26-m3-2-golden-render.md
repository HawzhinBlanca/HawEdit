# Adversarial pass 26 — M3.2, §4.3.6's golden-file render

M3.2 is the row §0 calls failure mode #3: *"FFmpeg's default shaping engine breaks Arabic-script
text. You will not catch it in code review — you will catch it when a client sees the burned-in
captions."* It was audited once, at D-061 on 2026-08-08. This pass tried to prove it false.

**It survived. 6/6 attacks caught**, including the two properties no audit had tested.

## The row's claims, attacked one at a time

Baseline verified green first; `tests/test_captions.py` + `tests/test_caption_timing.py`.

```
CAUGHT    production stops asking for complex shaping (§4.3.1)
           red: test_the_filter_always_sets_shaping_complex
CAUGHT    production stops pinning the font directory (§4.3.4)
           red: test_the_filter_references_the_font_directory
CAUGHT    the golden render itself renders the wrong way
           red: test_the_render_matches_the_golden_reference
CAUGHT    the comparison accepts anything
           red: test_a_differing_render_fails_the_golden_test, test_simple_shaping_fails_the_golden_test
CAUGHT    the comparison falls back to file bytes instead of decoded pixels
           red: test_the_render_matches_the_golden_reference
CAUGHT    a reference rendered by a broken build is enshrined
           red: test_simple_shaping_fails_the_golden_test, test_the_render_matches_the_golden_reference
6/6
```

The last one is the deepest and the one worth naming. `compare_golden_render` warns that *"a
reference produced by a broken build enshrines the bug it is meant to catch"*, and nothing had
tested that the suite refuses one. It does: regenerating `tests/golden/kurdish-caption.png` from a
`shaping=simple` render reddens **two** tests, because the negative control then finds the broken
render *matching* the reference and its `pytest.raises` fails. The reference is checked, not
trusted.

The filter string is duplicated — `subtitle_filter` (production) and `render_caption_png` (the
golden render) build it independently — which looked like a hole. It is not: mutating production's
copy in either of its two meaningful ways reddens immediately, so the string tests cover what is
there today.

## What was stale: "the reference re-renders byte-identical here"

D-061 recorded that. Re-measured on this machine, with
`ffmpeg 8.1.1-full_build-www.gyan.dev`:

```
--- file bytes (what a byte comparison would see) ---
golden   : 20,830 bytes
re-render: 21,847 bytes
identical: False

--- decoded RGB24 pixels (what the gate compares) ---
golden   : 6,220,800 bytes
re-render: 6,220,800 bytes
identical: True
```

The render is pixel-perfect and the **file is 1,017 bytes larger**. Not a defect — `decode_to_rgb`
exists precisely because *"PNG encoders differ between ffmpeg and zlib versions"* — but the
recorded measurement no longer describes this machine, and the design it justifies is now doing
real work rather than hypothetical work.

The other recorded number holds exactly. `shaping=simple` against the golden:

```
differing subpixels : 14,409 / 6,220,800  (0.2316%)
differing pixels    :  4,803 / 2,073,600  (0.2316%)
D-061 recorded      : 0.232%
```

## The finding: the decoded-pixel design was covered only by luck

Attack 5 above — forcing the comparison onto file bytes — is CAUGHT here. But it is caught
*because* this machine's encoder disagrees with the one the reference was made on. On a machine
whose encoder happened to agree, that regression would pass unnoticed, and the golden test would
be one ffmpeg upgrade away from failing on an encoder change that altered nothing a viewer sees —
the exact "cries wolf and gets disabled" outcome `decode_to_rgb`'s docstring is written against.

`test_the_comparison_runs_on_pixels_and_not_on_the_encoded_file` pins it without depending on any
of that. It repacks the reference at compression level **9** and level **1** — the same picture in
different bytes **by construction** on any ffmpeg — and requires the decoded comparison to accept
them and the byte comparison to refuse them.

Measured on this host: level 1 → 73,632 bytes, level 9 → 17,464, committed reference → 20,830; all
three decode to identical pixels.

**Rejected: comparing a repack against the committed reference.** That reintroduces the same luck
— measured here, even a default re-encode already differs from the committed bytes, so the
bytes-differ control would never fire on this machine and the test would be trusting the encoder
again.

## Mutation audit of the new guard — 4/4

```
CAUGHT    the regression: the comparison ignores ffmpeg and reads file bytes
CAUGHT    decode_to_rgb becomes a passthrough that returns the encoded file
CAUGHT    both repacks use the same compression level, control intact
CAUGHT    both repacks use the same level AND the bytes-differ control is dropped
4/4
```

The last pair is the D-162 rule applied: the control is mutated **together with the state it
describes**, not alone. Collapsing the levels is caught twice over — first by the bytes-differ
control, and if that is deleted, by the closing `pytest.raises`, which stops raising once the two
files are identical.

**A first version of this test was rebuilt after its own audit.** It compared a repack against
`GOLDEN`, and both "remove the compression level" mutations SURVIVED — because on this machine the
bytes differ anyway, so the flag changed nothing and the control could not fire. That is the same
machine-luck the test exists to remove, one level down. Reconstructed to compare two repacks
against each other, the control became demonstrable here and the audit went 4/4.
