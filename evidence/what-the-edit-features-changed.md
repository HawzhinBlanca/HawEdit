# What the edit features changed

> Measured 2026-08-29 on hawapc01, `ep29-chunk50min.mp4` — ZAR Podcast episode 29, 2560x1440,
> 50 minutes, the owner's own channel. `specs/pro-edit` T8.

## Before

The first clip this pipeline delivered from ep29, `work/ep29/ep29-chunk50-s68-69/`:

| | |
|---|---|
| duration | 34.65 s |
| visual changes | **0** |
| distinct crop rectangles | **1** — `crop_filter` fixed `crop_w`/`crop_h` before building its filter string, so a scale change was not merely absent but impossible |
| hook card | **0** — Stage 4 wrote `title_ckb` and the render discarded it |
| emphasis spans | **0** — uniform karaoke |
| internal silence | 1.20 s across three gaps, 3.5% |
| loudness | −14.0 LUFS |

Correct in every measurable respect and still an excerpt with subtitles. It passed a 3,278-test
suite, because **no test asserted anything about visual variety** — not a cut count, not a scale
change, not a shot duration.

## After

`work/ep29-deep/ep29-champ6-s76-77/`, cut from a champion transcript:

| | |
|---|---|
| duration | 64.1 s |
| visual changes | **11** — at 4.2, 10.0, 13.8, 19.2, 26.8, 35.0, 37.4, 39.1, 46.9, 52.3, 59.8 s |
| hook card | **1**, the judge's own Kurdish title on a plate |
| emphasis spans | **55** |
| loudness | −14.0 LUFS |
| editorial | hook 0.75, misleading-edit 0.10, self-contained, fidelity 1.00 |

## What each feature contributed, and what it cost to find

**The hook card was free and was being thrown away.** Stage 4 has always returned `title_ckb`.
Burning it is one ASS event. Its first render put white text across the subject's forehead,
readable only because of an outline — fixed with a 40% plate and a higher margin, found by looking
at the frame rather than the test.

**Punch-ins needed `sendcmd`, not a bigger expression.** ffmpeg evaluates crop's `w`/`h` once at
configuration and only `x`/`y` per frame, so a scale change could never have come from an
expression. All four options carry the `T` flag, verified on this build and on real footage before
being designed around.

**Punch-ins fired once in 35 s until the boundaries changed.** Cutting only on sentence starts gave
one change in a clip carrying two sentences. Switching to pauses of ≥120 ms between words — where
the speaker themselves broke — took it to three, and the rule that matters, never cutting inside a
word, held either way. **The feature passed its tests while doing almost nothing.**

**The source was already multi-camera and the selector was blind to it.** Stage 0 reports 271 shot
cuts in 50 minutes, one per 11.1 s. Judged spans average one per 19.8 s, so the editorial ranking
— hook score alone — is quietly biased toward visually flat footage. Of five judged candidates,
two had zero source cuts and one had six. **The clip that shipped first had none.**

**A punch-in beside a real camera cut is a glitch.** The source cuts at 26.01 s and a punch-in
landed at 26.78 s: the angle changes, then the crop jumps scale 0.77 s later. `SHOT_CUT_GUARD_MS`
drops any punch-in within 1.5 s of a source cut, symmetrically. Stage 0 had been finding these cuts
all along and nothing downstream used them.

## The honest verdict

**This is a good social clip and not a team-made edit.** It has a hook in the first two seconds,
cut rhythm, three real camera angles, emphasis, correct RTL captions and broadcast loudness. It is
still one continuous *moment*: no b-roll, no assembly across moments, no silence tightening, and
the crop follows the largest face rather than the person speaking (`BLOCKED.md` #4).

## The finding that outlives the feature

Every real defect in this work was invisible to the test suite and visible in the output: a default
crop rendering a wall, a framing floor derived from one source, punch-ins firing once in 35 s, a
double-cut 0.77 s wide. The suite stood at 3,300-odd tests and stayed green throughout.

`specs/pro-edit`'s impact map recorded the gap before any of it was built — *"no test asserts
anything about the visual variety of a render"* — and that remains the most useful sentence in the
feature. Watching the video is the test.
