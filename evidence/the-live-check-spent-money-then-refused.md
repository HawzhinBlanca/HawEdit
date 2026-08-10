# The live check spent money and then refused

> Measured 2026-08-10 on hawapc01 against `f189b19`, ffmpeg 8.1.1-full, no API key — the spend is
> demonstrated by where the refusal sits, not by making the calls.

## The claim

`README.md`:

```bash
.venv/bin/python -m hawedit.smoke     # two real calls, ~$0.003
```

> It runs §3 Stage 3 Path A over a built-in Sorani sample and §3 Stage 4 on the top candidate,
> then prints the Kurdish title it got back.

## What it did

`smoke.py`'s Stage 4 block, *after* the Path A block that makes both real calls:

```python
top = candidates[0]
print("\n==> Stage 4")
if args.video is None:
    print("✗ Stage 4 needs --video; text-only visual judging is refused", file=sys.stderr)
    return 1
```

`--video` appears nowhere in the README. So the documented invocation spent the money, printed the
candidates, and stopped — no Stage 4, no Kurdish title. D-071's shape: a refusal `argv` settles,
placed after the billed call.

## Why a video is not optional, and why none here will do

§3 Stage 4 judges real source pixels; `AUDIT_REPORT.md` records the text-only refusal as
deliberate. The built-in sample spans **0..13,000 ms**. The only Kurdish video in the repository is
**4.162 s**. Extracting judge keyframes from it:

```
(0, 4000)     20 frames, timestamps 100, 300, 500, 700, 900, 1100 …   all inside the file
(0, 13000)     6 frames, timestamps 325, 975, 1625, 2275, 2925, 3575     all inside the file
(5000, 13000) KeyframeError: ffmpeg failed to extract judge keyframes (…)
```

A shorter video either fails outright or hands the judge frames stamped across a span the file does
not contain. `BLOCKED.md` #20 records what would resolve it — a recording of the sample, at least
13 s — and what was refused instead.

## The fix

The `--video` check, and the file-exists check with it, now run immediately after the key check:
before the cost estimate, before the confirmation prompt, before anything billable. Exit **2**, the
code this project uses for *refused before doing anything*.

Above the confirmation on purpose: being asked to authorise a spend on a run that cannot finish is
its own defect.

## Proof

```
baseline green: True

RED  the defect restored: the refusal moves back after the billed Path A calls
RED  the missing-video refusal goes away entirely
RED  a video path that does not exist is accepted
RED  the guard moves below the confirmation: still before the spend, but the user is asked
     to authorise a run that cannot finish
RED  the README stops naming --video on the documented invocation
RED  the README points at a BLOCKED entry that does not exist

6/6
restored and green: True
```

The artifact of the fix is a request that never happened: every refusal test installs a stand-in
for `PathADiscovery` that raises if it is reached at all, so a guard that slipped back below the
spend escapes as an error rather than passing quietly. The control requires the legal invocation —
with a real `--video` — to get through the guard and *arrive* at that stand-in, because a `main`
that refused everything would satisfy all three refusal tests.

## Three survivors first time, and only one was a bad mutation

The audit was 3/6. Two survivors were real gaps in my own work:

* nothing bound the README's documented invocation to `smoke.py`'s requirement;
* nothing checked that a `BLOCKED.md #N` cited in the README exists — mutating `#20` to `#21`
  passed, because `test_every_blocked_row_points_at_a_live_blocked_entry` reads PROGRESS's
  `BLOCKED` rows and nothing else.

The third was mine: I "moved" the guard below the confirmation by inserting a no-op line, which
changes nothing at all. Moving a block is a delete **plus** an insert, and applying either half
alone measures something else — the harness now takes a list of edits for a single mutation.

## Two existing tests changed, and both got stronger

`test_it_sends_nothing_until_a_human_agrees` and `test_a_declined_prompt_at_eof_also_sends_nothing`
drove `main([])` as far as the confirmation prompt, which the new guard short-circuits. They now
carry a `--video`, so the run they decline is one that could otherwise have proceeded.

Gate: `VERIFY OK — hawedit gate green`, 1494 tests (floor 1488 → 1494).
