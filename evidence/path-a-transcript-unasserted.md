# Path A's transcript could be deleted entirely and the whole suite stayed green

> Measured 2026-08-09 on hawapc01 against `a057cf7`, against a green 1,136 baseline.

M2.3's row says Path A *"sends the **whole** normalized transcript — a test asserts every fragment
reaches the judge, because sending a subset is the exact failure §3 built the dual path to prevent
and would be invisible in the output."*

The behaviour is correct at HEAD. The test guarding it was blind.

## The measurement

`text=transcript.text_ckb` → `text=""`, so the judge receives a timing table and no Kurdish text:

```
pytest tests/test_path_a.py   ->  21 passed
pytest tests/                 ->  exit=0,  0 FAILED
```

Truncating instead of deleting behaves the same way. §3 built the dual path precisely because a
subset would be invisible in the output — the candidates still come back looking reasonable — and
the test written to catch that could not.

## Why the test was blind

```python
for fragment in ("ڕۆژنامەوانی", "گرنگە", "بکەین"):
    assert fragment in api.prompt
```

All three are entries in the fixture's `words` tuple, and `_timing_table` renders every word above
the transcript:

```
text_ckb: ڕۆژنامەوانی کوردی لە هەولێر. ئەمە زۆر گرنگە بۆ ئێمە. با باسی بکەین.
words   : ئەمە, بکەین, ڕۆژنامەوانی, کوردی, گرنگە
fragments ONLY in text_ckb: لە, هەولێر, زۆر, بۆ, ئێمە, با, باسی
```

So `fragment in api.prompt` was satisfied by the timing table alone. The fixture *deliberately*
carries seven fragments absent from `words` — exactly the ones that would discriminate — and the
test asserted none of them. It sampled precisely the fragments that could not tell the two cases
apart.

## The fix

Assert the **whole** `text_ckb` verbatim. A substring check on the complete transcript cannot be
satisfied by a timing table, and it needs no hand-maintained fragment list.

The discriminating fragments are still checked, but **derived at runtime** as `text_ckb` minus
`words`, with an assertion that the set is non-empty — so a future fixture whose text adds nothing
beyond its words fails loudly rather than silently blinding the test a second time.

## The control, because the fix could have caused the opposite defect

A prompt that dropped the timing table and kept the text would satisfy everything above. The test
now also requires a timing row.

```
CAUGHT   text is dropped entirely
CAUGHT   text is truncated to a subset
CAUGHT   the timing table is dropped (the control)

3/3
```

## A claim I could not reproduce, recorded because it was alarming

The same agent reported that a `RawTranscript` reaches `countTokens` before Kurdish invariant #3
refuses — *"endpoints hit: ['gemini-2.5-pro:countTokens'] and RAW text in an emitted request body:
True"*. That would be raw Kurdish transcript text leaving the machine.

Measured with the suite's own recording transport:

```
  discover(raw)        refused: raw transcript passed to a model input: inde…
      endpoints hit: []   RAW text in a body: False
  build_request(raw)   refused: raw transcript passed to a model input: inde…
      endpoints hit: []   RAW text in a body: False
```

`discover` calls `_prompt` first, and `_prompt` calls `assert_model_input` before anything is
assembled — so `count_parts` is never reached. Invariant #3 holds at the door on both public entry
points, and the claim is **refuted as stated** rather than carried forward.

This is the third consecutive pass whose framing needed correcting before it was actionable — after
redundancy inflating a count threefold (D-079) and a mutation caught for an unrelated reason reading
as protection (D-082). It is the first where the alarming half was simply wrong, which is the more
useful reminder: an agent report is a lead, and a lead about data egress deserves reproduction before
it is repeated, not after.

## What this pass found that is not fixed here

Nine other rows were audited in the same run, all against green baselines: 132 claims, 41 falsified,
34 truly unprotected, 23 demonstrating a wrong artifact. Notable and unverified by me:

* **M5.1** — the survivor floor is checked against `len(index)`, never the retrieved set, so
  `retrieve_k=3` with `keep=5` returns 3 survivors through the public `VisualComposer`. Not reachable
  from the CLI, which never passes `retrieve_k`.
* **M5.3** — `assert_sv6d_within_window` accepts `"speaker gestures at 9999s, held over 1s"` on a
  0..1400 ms window, because "over 1s" parses as an in-window absolute time. That re-licenses the
  exact claim the row headlines as closed.
* **M2.4** — deleting `assert_captions_within_clip` is caught only by **ruff** (unused import), not
  by any behaviour test; an import-preserving mutation ships a caption-free MP4 with
  `captions_burned_in=True`.
* **M1.7 / M0.15** — evidence-file numbers that do not reproduce, including the `waw_initial_words:
  491` discrepancy still open from the second pass.

Each needs its own verification before action, on the evidence of this iteration.

Gate: `VERIFY OK — 1136 passed, 0 skipped`.
