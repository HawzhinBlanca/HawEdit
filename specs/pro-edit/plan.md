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

## Learned while implementing

**T4 silence tightening is measured as not worth building on this material, and the row stays
open rather than being quietly dropped.** On the delivered 64.1 s champion clip: seven gaps over
250 ms totalling 2.78 s (4.3%), three over 400 ms totalling 1.52 s (2.4%), and **zero over
600 ms**. The longest pause in the clip is 580 ms, which is a breath rather than dead air — cutting
it would make the speech sound clipped, which is a worse defect than the 2.4% it saves.

The cost is not small either. Removing time couples to three other timing systems at once: the
punch-in `sendcmd` timestamps are in output time, the crop `x` expression is a function of `t`,
and every ASS caption carries absolute stamps. A silence cut that shifts one and not the others
desynchronises the clip, and the failure would be invisible in a test and obvious in the video.

**Where it would earn its place** is material with real dead air — a hesitant speaker, an
interview with long thinking pauses. This source is a produced podcast with a fluent guest. The
threshold for revisiting is a measured clip with gaps over 600 ms, which this one does not have.

**T5's boundaries changed after the row was flipped.** `punch_in_schedule` was fed sentence starts
and fired *once* in a 34.65 s clip carrying two sentences. It now takes `cut_points_ms` — pauses of
at least 120 ms between words — and a `SHOT_CUT_GUARD_MS` that drops any punch-in within 1.5 s of a
camera cut the source already made. Both changes came from watching the render, not from a failing
test.

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
