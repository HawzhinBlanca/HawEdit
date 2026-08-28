# Research — a cut that reads as edited

## What the render actually produces, measured

The ep29 delivery, `work/ep29/ep29-chunk50-s68-69/`:

| property | value | how it was measured |
|---|---|---|
| camera cuts inside the 34.65 s clip | **0** | `select='gt(scene,0.25)'` over the source span |
| distinct crop rectangles | **1** | `crop_filter` emits one `crop=W:H:x:y`; only `x` is a time expression |
| vertical crop movement | **none** | `y` is an int, computed once |
| scale changes / punch-ins | **structurally impossible** | `crop_w`, `crop_h` are locals fixed before the filter string is built |
| internal silence > 250 ms | 3 gaps, 1.20 s = **3.5%** of the clip | word timings in the delivered contract |
| caption events | 30 popup events, uniform karaoke | the delivered `.ass` |
| judge's `title_ckb` | written by Stage 4, **discarded** | present in `stage4/*/verdict.json`, absent from the render |

So the delivered artifact is one unbroken shot, one crop size, a horizontal pan and karaoke
subtitles. That is an excerpt with captions, not an edit.

## What the spec says

`BLUEPRINT.md` §3 Stage 6 is one sentence: *"Reframing, captions, encode. Caption requirements in
§4.3 are not optional. Vertical reframing tracks the active speaker from diarization plus face
detection; add SAM 3 only if face-centred cropping proves insufficient on real footage."*

There is **no** §3 requirement for cutting, pacing, titles or assembly, and no § forbidding them.
Everything in this feature is therefore a deliberate extension and needs an ADR — the same footing
as D-254's target range, which BLUEPRINT also does not state.

## Symbols

| symbol | file | role |
|---|---|---|
| `crop_filter` | `render.py:295` | builds the single `crop=…,scale=…` chain |
| `vertical_framing` | `render.py` | D-258's per-clip crop rectangle |
| `render_clip` | `render.py:512` | one input, one filter chain, one encode |
| `chunk_caption_events` | `captions.py:585` | popup grouping, uniform styling |
| `CaptionTheme`, `VIRAL_THEME` | `captions.py:127` | colours, size, margins |
| `Boundary`, `assert_boundary_invariant` | `boundary.py:178` | §5 in/out, invariant #2 |
| `dead_air_flags` | `pipeline.py` | *flags* internal silence, never cuts it |
| `Clip.output` | `clip.py` | carries `title_ckb`, `crop_target`, `caption_style` |

## Risks

- **Splicing is what `misleading_edit_risk` measures.** Fifteen of fifteen verdicts scored 0.10 on
  single continuous spans. An assembled reel is a different artifact and the judge must score the
  assembly, not the source spans, or the score describes footage nobody will watch.
- **Kurdish invariant #2** governs sentences, not shots. Cutting *within* a sentence for pacing is
  new territory: the invariant is about never rendering an incomplete sentence, and a punch-in
  does not break it, but silence-tightening changes word timings the captions are keyed to.
- **Speaker-tracked reframe is blocked**: `pyannote/speaker-diarization-community-1` is gated and
  the licence is unaccepted, so the crop follows the largest face rather than the talker.
- `crop_filter` has 19 call sites and a golden pixel test (§4.3.6); a time-varying crop size
  changes the filter string every existing test asserts on.
