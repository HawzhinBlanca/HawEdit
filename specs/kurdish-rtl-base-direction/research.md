# Research — Kurdish caption base direction (kurdish-rtl-base-direction)

Date 2026-11-17. Branch `fix/kurdish-rtl-captions` from `0ea5158`. Host HawaPC01, Windows 11,
`.venv` CPython 3.12, ffmpeg 8.1.1-full (gyan.dev, libass + HarfBuzz + FriBidi), font
`assets/fonts/NotoNaskhArabic-Regular.ttf`. Serena failed to connect (timeout), so symbols were
mapped with grep; no `find_referencing_symbols` output exists for this feature.

## Defect (rendered today; grids and both probe scripts in `captures/`)

libass lays every caption line out with a left-to-right base direction because all three Style
writers emit `Encoding = 1`. Measured on the committed golden sentence and three more:

| Style | What a Kurdish viewer sees today |
|---|---|
| `WORD_HIGHLIGHT` | Words in reversed order (first word leftmost). Known since D-269, kept "for byte-identical regression tests" |
| `LINE`, `VIRAL_POPUP`, `RTL_WORD_HIGHLIGHT` | Word order right; sentence-final `.` drawn at the sentence start (right end). Not recorded anywhere before today |
| any style, line with Latin word or digits | Latin/number segment jumps to the wrong end |

`؟` (U+061F) is unaffected: it is a strong right-to-left character.

`DEFAULT_CONTENT_TYPE` is `PODCAST` (`content_type.py:96`) and the PODCAST, INTERVIEW and SOCIAL
profiles default to `CaptionStyle.WORD_HIGHLIGHT` (`content_type.py:61,70,88`). Nothing remaps
it. A default run therefore burns reversed Kurdish captions.

## What fixes it (same host, same binary)

| Variant | Golden / question / mixed | Line starting with a Latin word |
|---|---|---|
| Style `Encoding = -1` | correct in all four styles | still wrong (auto-detect picks LTR) |
| `{\fe-1}` per Dialogue | correct in all four styles | not tested |
| U+200F at line start, Encoding 1 | still wrong | — |
| `Encoding = -1` **and** leading U+200F | correct | **correct** |

## Symbols

- Style writers, all in `src/hawedit/captions.py`: theme style (`:245`, ends `{mv},1`), plate
  style (`:272`, ends `{mv},1`), width-probe `Default` style (`:1024`, ends `0,0,0,1`).
- Dialogue writers: `captions.py:1028, 1845, 1855, 1886, 1906, 1918`.
- Dialogue readers that must ignore a leading U+200F: `captions.py:2437, 2543, 2598`
  (`verify_caption_text` / `verify_caption_integrity`), `measure.py:495`, `sanity_gate.py:124`.
- `build_ass` (`captions.py:1546`) callers: `assembly.py:308`, `captions.py:2703`,
  `pipeline.py:2410, 4300`, `proposals.py:596, 767, 949`. Signature does not change.
- Stage: §3 Stage 6 render; rule: §4.3, safeguard §4.3.6 (golden PNG).

## Tests and references that pin today's output

- `tests/golden/`: `kurdish-caption.png` (full stop on the wrong side),
  `kurdish-viral-karaoke.png` (words reversed), `kurdish-hook-card.png`,
  `kurdish-caption-fixture.png`; digests pinned at `tests/test_captions.py:543-551`.
- `tests/test_captions.py:2193` replaces the literal `"2,40,40,200,1"`.
- Golden tests are `skipif(find_ffmpeg() is None)`; on a host without ffmpeg they do not run.

## Risks

- `Encoding = -1` and whole-line bidi need a recent libass. Verified only on this host's
  ffmpeg 8.1.1. The CI Linux build (`scripts/fetch-ffmpeg.sh`, zackees v8.0) is unverified;
  the golden comparison is what will say so.
- Goldens are enforcement surface and anti-cheat forbids editing one "so it matches buggy
  output". Here the committed references are the buggy output; replacing them needs the
  owner's explicit approval and `.codystem-allow-self-edit`.
- D-269 clause 1 must be superseded by a new ADR (next free number is D-334).
- Out of scope, seen in the same frames: Latin words fall back to a much larger bold font.

Answers to: §4.3, §4.3.6, D-269, D-307. No BLOCKED item.
