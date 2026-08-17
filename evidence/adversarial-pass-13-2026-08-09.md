# Adversarial pass #13 — the pixels Stage 4 is charged for

> Run 2026-08-09 on hawapc01 against `4f7bafd`.
> Target: **M2.9**, DONE — never attacked, and the only row whose artifact is a *billed* request.

## The cell's numbers reproduce exactly

```
extract_judge_frames(kurdish-speech-3cuts.mp4, 0, 4162, count=6)

frames             6
timestamps (ms)    347 / 1040 / 1734 / 2428 / 3122 / 3815      the cell, to the millisecond
spacing (ms)       693 694 694 694 693
sizes (bytes)      3332 3332 2624 2624 3424 3424               the cell: 2,624–3,424
all start FFD8     True
mime types         image/jpeg
distinct payloads  3                                           three static shots
payload is bytes   True
```

Nothing in the row had to be withdrawn.

## Four of ten mechanisms are held

```
MISSED  frames are sampled from the start of the media, not the candidate
CAUGHT  every frame is stamped at the same moment
MISSED  a span with no duration is accepted
CAUGHT  a count outside 1..20 is accepted
MISSED  a missing ffmpeg returns no frames instead of refusing
MISSED  an ffmpeg failure returns no frames instead of refusing
MISSED  more frames than asked for are accepted
CAUGHT  JPEG bytes are declared as PNG
MISSED  a text-only judge is charged for keyframes anyway
CAUGHT  a multimodal judge is sent no frames at all

4/10
```

`tests/test_keyframes.py` is 27 lines and two tests, for a module whose cell credits it with four
refusals.

## The timestamps are the request echoed back

The existing test asserts `[500, 1300, 2100, 2900, 3700]` for `100..4100`. Those are arithmetic:

```python
timestamp_ms=min(out_ms, round(in_ms + (index + 0.5) * step_ms))
```

Replace `-ss in_ms` with `-ss 0` and every one is unchanged. The bytes a billed multimodal judge
receives could then come from anywhere in the media while the request says otherwise. M3.4's lesson —
*"`RenderResult.duration_ms` was the request echoed back and the file was never opened"* — one module
over.

The fix asserts the payloads, using the fixture's three static shots:

```
0..1400     sha 46f2c52ce626999c   3,332 bytes
1400..2800  sha 51f35b218c7a4534   2,624 bytes
2800..4162  sha d700e83a931dfb52   3,424 bytes
```

Three spans, three pictures. Plus a control that names the substitution: the last shot's frame must
differ from the first shot's specifically, which is what `-ss 0` makes identical.

## The refusals the cell claimed

"A span with `out_ms <= in_ms`, a count outside 1..20, and a missing ffmpeg are each refused rather
than returning an empty tuple that would read as 'no frames here'." Only the count *ceiling* was
tested. Now: the zero-length and inverted span, `count=0`, a monkeypatched-away ffmpeg, and a source
ffmpeg cannot decode — the last two because `()` is exactly what a text-only request looks like.

This readiness branch already carries D-107's stronger namespace boundary: every ffmpeg call writes
into a unique private directory and enumerates only that call's files. The adapted product-path test
extracts 8 frames and then 2 through the same caller work directory, requires exact counts for both,
and proves no private frame directory remains. Caller-owned stale files are independently pinned by
`test_keyframes_never_promote_stale_outputs_from_a_prior_call`.

## The gate's other direction

`getattr(judge, "requires_keyframes", False)` had a test for `True` and none for the attribute being
absent, so making the gate unconditional passed. A text-only model would be billed for up to twenty
inline images, which §3 Stage 4's cost model counts. Now pinned with a judge that never heard of the
flag — the case the `False` default exists for.

```
after: 10/10
```

No production code changed. Every mechanism was already right; six were unheld.

Gate: `VERIFY OK — 1296 passed, 0 skipped`.
