# Plan — a cut that reads as edited

## The defect in one line

The render produces one unbroken shot at one crop size with karaoke subtitles, and calling that a
social edit was wrong.

## Approach

**Build the cheap, safe things first and the risky thing last.** The hook card, emphasis and
silence tightening cannot change what anyone is understood to have said. Punch-ins change only
how the same continuous speech is framed. Assembly changes which words sit next to which, and
that is the one the editorial gate exists to police — so it goes last, after the safe work has
already made the clip look edited.

**Punch-ins are a crop *sequence*, not a crop.** `crop_filter` fixes `crop_w`/`crop_h` before it
builds the filter string, so a scale change is impossible today. The change is to emit a chain
whose crop dimensions are time expressions too, keyed to sentence boundaries the run already has.
Scale changes land on sentence boundaries (AC-2) because a cut mid-word reads as a glitch.

**The hook card is free and we are throwing it away.** Stage 4 returns `title_ckb`; the ep29
verdict wrote a real Kurdish title and the render never read it. Burning it over the opening is an
ASS event, not a new subsystem.

**Silence tightening moves the captions or it is a bug.** Word timings key the `.ass`, so removing
a pause without shifting every later event desynchronises the whole clip. AC-5 records the removed
total because otherwise a delivered duration can no longer be reconciled with its source span, and
§8.3 asks for that invariant on every shipped clip.

**Assembly is judged as an assembly.** Fifteen of fifteen verdicts scored misleading-edit 0.10 on
single continuous spans. A spliced reel is a different artifact; scoring the source spans and
shipping the assembly would be a verdict about footage nobody watches. So the judge sees the
assembled span set, and §2's thresholds apply to that verdict (AC-7, AC-8).

## Divergence from BLUEPRINT

**Yes, and it is the point.** §3 Stage 6 says *"Reframing, captions, encode."* It does not ask for
cutting, pacing, titles or assembly, and it does not forbid them. Every task here is an extension
on the same footing as D-254's target range, and T1 records it as a decision with the owner's
name rather than smuggling it in as an implementation detail.

## Risks

- **Assembly is exactly what `misleading_edit_risk` measures.** It may score badly and the clip may
  then be refused — which would be the gate working, not a regression. T8 records the number either
  way.
- **The golden render is a pixel comparison** (§4.3.6). A time-varying crop changes the filter
  string; the golden must keep passing on the single-framing path, and that is AC-2's non-regression
  test rather than a licence to touch the reference.
- **Speaker tracking stays blocked.** `pyannote/speaker-diarization-community-1` is gated and
  unaccepted, so T7 cannot be built and the reframe must keep saying `face_tracked` rather than
  claiming what it does not do.
- **Cutting within a sentence is new territory.** Invariant #1 governs the transcript and #2
  governs sentence completeness; neither speaks to pacing. Silence tightening removes time between
  words *inside* a rendered sentence, so the guard is that captions stay keyed to the words.

## Decisions, settled by the owner 2026-08-28

1. **Both punch-ins and multi-moment splicing.** The owner asked for both, having been told that
   splicing is the thing the misleading-edit metric penalises.
2. **All four techniques**: hook card, silence tightening, speaker-tracked reframe, emphasis
   captions. Speaker tracking is blocked on the pyannote licence and stays a stub that refuses to
   overclaim until that clears.

Approved-by: Hawa (in chat, 2026-08-28) — punch-ins + splicing, all four techniques.
