# Plan — Reel Visual Quality

## Status
Approved-by: User (2026-10-14)

### Decisions Recorded:
1. **Wide shots:** Per-shot adaptive framing with zoom up to `MAX_VERTICAL_ZOOM = 1.5` cap via `sendcmd`.
2. **Caption vertical position:** Chest level (`margin_v` ~ 480-500px, avoiding the bottom platform UI occlusions).
3. **Hook badge:** Clean vector styling in ASS subtitles.

## Goal
Real renders of ep29 that pass the **real** pipeline gates plus a gate that actually measures
framing, and look right to a human reviewer. "Flawless" is not testable. The acceptance target is
the EARS criteria in `spec.md` plus a per-shot contact sheet signed off by the owner.

## Tasks (one at a time, test-first, `bash scripts/verify.sh` after each)

### T1 — Stop using the demo scripts (deletion)
Delete `scripts/run_tier3_demonstration.py` and `scripts/run_bremer_story_demonstration.py`. They
hardcode editorial, ASR and QC values (research §0). Run the same two spans through
`python -m hawedit.pipeline` with NVENC and record what the real `reconcile_delivery` /
`render_critic` say. That gives a measured baseline before any fix.

### T2 — Fail-stop in `GeminiStoryEvaluator`
`condenser.py:258-277,571`: a missing `virality_score` / headline / summary / per-sentence
`importance_score` / `keep` raises `StoryCondensationError` instead of using a default. Test feeds a
truncated model response through the existing `transport=` seam. That tests the parser itself; the
parser is not mocked.

### T3 — Per-shot vertical framing
`median_face_box` grows a per-shot variant: medians per segment between `shot_cuts_ms`.
`crop_filter` switches crop size/y at each cut using the same `sendcmd` mechanism punch-ins already
use. That mechanism was proven on real footage (`render.py:1051`). The 1.5x cap (D-258) is kept.
Wide-shot handling follows decision 1. Diverges from `median_face_box`'s documented one-placement
rule → ADR in `DECISIONS.md`.

### T4 — Gate measures framing, not just face presence
`check_face_presence` → also measures face height share and the face's vertical position per shot,
and fails below a floor. The floor is calibrated on measured frames from T1 (close-up vs wide). It
is not picked by hand. Duration check stops rounding. Production runs use `strict_fail_stop=True`.

### T5 — Caption and hook placement/style
Caption `margin_v` default moves to the decided safe band (decision 2), with a SanityGate check
that fails captions inside the platform UI zone. Hook banner restyle per decision 3.

### T6 — Re-render and review
Re-run T1's two spans through the real pipeline. Produce a contact sheet with one frame per shot.
Only `verify.sh` green + CI + owner sign-off on the sheet = done.

## Decisions for the owner
1. Wide shots: per-shot zoom to the 1.5x cap / blurred-fill layout per shot / prefer story spans
   without wide shots.
2. Caption vertical position: chest level (~y 1250–1400 of 1920) / keep bottom but above UI band.
3. Hook badge: ASS vector rounded badge (no new assets) / PNG overlay (needs provenance).
