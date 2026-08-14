> **Two independent passes were both numbered 24.** This file was created separately on each
> branch on the same day, for different work — the same root cause as the 37 colliding
> D-numbers D-200 records, and for the same reason: two lines counting on from one base.
> Both records are kept whole below rather than one being chosen, because each is a
> measurement and neither supersedes the other.

## Pass 24 — harness branch

# Adversarial pass #24 — M6.2, the HARD/SOFT rule itself

> Measured 2026-08-10 on hawapc01 against `5eba372`, Python 3.11 in `.venv`.

M6.2 is **DONE** and had never been attacked — one of six such rows. Its evidence is a sweep:

> invariant #2 swept over 78,125 combinations covering every sign of all seven optional
> `BoundaryInputs` fields (D-078)

That proves `final_in <= anchor_in <= anchor_out <= final_out` across every combination of signs.
§3 Stage 5's SOFT rule is not only a bound, though — it is a candidate set and a **selection**:

```
final_in  = earliest of { anchor_in, vad_onset − 120 ms, preceding shot_cut within 400 ms, … }
final_out = latest   of { anchor_out + 200 ms tail, natural silence, following shot_cut … }
```

A wrong selection still only moves the edge outward, so the invariant still holds and the sweep
still passes.

## The pass

```
baseline green: True

CAUGHT    §3's 400 ms shot-cut window becomes 4000
CAUGHT    §3's 120 ms VAD lead-in becomes 1200
CAUGHT    §3's 200 ms tail becomes 2000
CAUGHT    the tail is dropped, so anchor_out alone competes for the out point
CAUGHT    speaker_turn_start stops being an in-point candidate
CAUGHT    natural_silence stops being an out-point candidate
SURVIVED  a cut exactly at anchor_in stops counting as preceding
SURVIVED  the nearest preceding cut wins instead of the earliest
SURVIVED  the nearest following cut wins instead of the latest
CAUGHT    the clamp at 0 is removed, so a clip may start before the media

7/10
restored and green: True
```

## The two that matter

Every existing shot-cut test supplies **exactly one cut** — precisely the input where `min` and
`max` agree. With three cuts inside the 400 ms window:

```
preceding  (ANCHOR_IN − 350, −200, −50)    earliest  9650    nearest  9950
following  (ANCHOR_OUT + 50, +200, +350)   latest   14350    nearest  14200
```

Taking the nearest preceding cut starts the clip 300 ms late, mid-shot. Taking the nearest
following cut leaves the 200 ms tail as the winner and ends it 150 ms early. §3 says *earliest* and
*latest* in the frozen blueprint, so neither is a matter of taste — and both kept Kurdish invariant
#2 intact with 1,501 tests green.

Pinned now, each with a control that discriminates: the single-cut case must still yield the single
cut, and a following cut closer than the tail must lose **to** the tail — so neither test can pass
by the out point simply ignoring its candidates.

## The third survivor is a bad mutation of mine

`cut <= anchor_in` → `cut <` changes nothing an input can observe. `min(in_candidates, …)` returns
the *first* minimum and `(anchor_in, None)` is appended first, so a cut exactly on the anchor loses
the tie to the anchor whichever comparison is used:

```
cut exactly at anchor_in : final_in=10000  in_extended_by=None
cut exactly at anchor_out: final_out=14200 out_extended_by='tail'
```

Writing a test for it would pin a tie-break §3 does not specify. Recorded rather than pinned. Sixth
bad mutation of mine this session, after D-137, D-141, D-144, D-147 and D-149.

## What survived

Every numeric constant §3 names — 120 ms, 200 ms, 400 ms — reddens when changed, as do dropping
the tail, dropping either optional candidate, and removing the clamp at 0. The row's claim about
the invariant sweep is true. What it never claimed, and nothing checked, was the selection.

No production code changed. **9/9 after.**

Gate: `VERIFY OK — hawedit gate green`, 1503 tests (floor 1501 → 1503).

---

## Pass 24 — readiness branch

# Adversarial pass 24 - release publication cannot replace an empty winner

Date: 2026-08-10
Baseline: `5b3442f491ac79868f6a2281c6cfb85ffbd59041`

## Finding

The release builder checked that its final directory did not exist and then called `os.rename`.
The test covered a populated winner, which POSIX already refuses to replace. It did not cover an
empty directory created by another process after the check. POSIX `rename` may replace that empty
directory atomically, so the operation was atomic but not write-once.

That distinction is load-bearing for release output: an external process can reserve the final
name between a successful preflight and publication, and the release process must preserve that
winner regardless of whether it has written its first file yet.

## Fix and proof

Release publication now delegates to the shared native no-replace primitive introduced by
adversarial pass 23. A kernel `EEXIST`/`ENOTEMPTY` becomes the same bounded `ReleaseError`; other
filesystem failures keep their existing domain error. There is no check-then-rename fallback.

The discriminating regression creates an empty final directory, records its inode, and invokes the
real release publication function. The call refuses, the inode and empty contents remain unchanged,
and the private staged wheel remains intact. The older populated-winner control still passes.
