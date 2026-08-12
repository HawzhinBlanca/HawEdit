# Three of four checkpoints declare what the comment claimed for all four

`visual_index.py` justified `TEMPORAL_PATCH_FRAMES = 2` with a statement of measured fact:

> All four §7 visual models ship `do_sample_frames: true` with `fps: 2`, `min_frames: 4` and
> **`temporal_patch_size: 2`** in `video_preprocessor_config.json`

`video_input.py` repeats it, and D-060's table was derived from it. One third of it is false.

## The measurement

Read from the four `video_preprocessor_config.json` files on this disk:

| model | role | fps | min_frames | temporal_patch_size |
|---|---|---|---|---|
| `Qwen3-VL-Embedding-2B` | visual_embedding | 2 | 4 | 2 |
| `Qwen3-VL-Reranker-2B` | visual_rerank | 2 | 4 | 2 |
| **`MCG-NJU/VideoChat3-4B`** | visual_discovery | 2 | 4 | **1** |
| `MCG-NJU/TimeLens2-4B` | temporal_evidence | 2 | 4 | 2 |

```
distinct fps declared                : [2]        -> the comment is right
distinct min_frames declared         : [4]        -> the comment is right
distinct temporal_patch_size declared: [1, 2]     -> the comment is wrong
```

"All four" is right about the count, `fps: 2` and `min_frames: 4` hold for all four, and
`temporal_patch_size: 2` holds for **three**.

## The constant is right; its justification was not

`TEMPORAL_PATCH_FRAMES = 2` stays. It is not a shared declaration — it is the **strictest** of
them, and that distinction is the whole reason it is correct:

`extract_window_frames` extracts a window **once**, and D-140's `_FrameCache` hands those same
files to the embedder *and* the reader — `VideoChat3Reader` takes `read_frames` precisely so that
"the frames a window was *embedded* from in Stage 2 are the frames it is *read* from here". One
extraction feeding models with patches of 1 and 2 must satisfy the coarser one. Trimming to a
multiple of 2 costs VideoChat3 at most one frame it would have accepted, and saves Qwen from
padding an odd count by repeating the last frame — a frame that was never filmed, which is the
defect D-060 exists to prevent.

So nothing in the behaviour changes. What changes is that the comment now says why the number is
2, instead of asserting something about the weights that is not true of one of them.

## Pinned, so it cannot drift again

Two tests read the constants back off the checkpoints, skipped when the weights are absent (CI
installs no models, and D-095 made the floor count *passed*, so a skip is safe):

* `test_the_declared_rate_and_minimum_are_the_checkpoints_own` — `DECLARED_SAMPLING_FPS` and
  `_MIN_SAMPLED_FRAMES` are the single value every config declares.
* `test_the_temporal_patch_constant_is_the_strictest_the_checkpoints_declare` — asserts
  `TEMPORAL_PATCH_FRAMES == max(declared)`, **not** that they agree.

The second carries its own control: it also asserts the declared sizes are **not** all equal. If a
future checkpoint set made them uniform, `max` would become indistinguishable from "what they all
declare" — which is exactly the claim that was wrong here — and the test says so by name rather
than passing quietly.

## Mutation audit — 3/3 lint-clean

```
CAUGHT   the temporal patch drops to the loosest checkpoint instead of the strictest
CAUGHT   the declared rate stops matching the checkpoints
CAUGHT   the minimum sampled frames stops matching the checkpoints

file restored byte-identical: True
3/3 caught lint-clean
suite after restore: GREEN
```

Before these tests existed, all three constants could be changed to a wrong value with the whole
suite green — they were justified by a comment and checked by nothing.

## The first fix was pinned to weights, and CI refused it

The tests above were first written to read the four `video_preprocessor_config.json` files
directly, behind `pytest.mark.skipif(not _declared_video_preprocessors())`. **Locally green,
1621 passed. On the runner:**

```
1619 passed, 2 skipped, 86 warnings in 80.33s
REFUSED: only 1619 tests passed against a floor of 1621 (2 skipped of 1621 collected).
Either 2 test(s) disappeared, or a skip condition is creeping.
```

Exit 6. **Main was red for one commit** ([5995d87](../../commit/5995d87)).

The gate was right and the mechanism is D-095's: the floor compares **passed**, never `collected`,
*"the two differ by exactly the skips, which is the case the ratchet exists to catch"*. A test that
passes where the weights are and skips where they are not can never count toward a global floor —
it ratchets the bar on the machine that has them and fails on the machine that grades. This repo
had **zero** skips before; the two I added were the first, and they broke the invariant
immediately.

**The redesign, which is better than what CI rejected.** The declarations move out of prose and
into `DECLARED_VIDEO_PREPROCESSORS` — a table in `visual_index.py`, checked by three tests that run
**everywhere**:

* the rate and minimum are the single value every recorded checkpoint declares;
* `TEMPORAL_PATCH_FRAMES == max(recorded)`, with the control that the sizes are **not** all equal;
* every §7 model carrying a visual role appears in the table — a model missing from it would drop
  out of the `max` silently, which is the same defect one level up.

The table itself was verified against all four checkpoints on disk before committing:

```
Qwen3-VL-Embedding-2B   recorded == disk  OK
Qwen3-VL-Reranker-2B    recorded == disk  OK
MCG-NJU/VideoChat3-4B   recorded == disk  OK
MCG-NJU/TimeLens2-4B    recorded == disk  OK
recorded table matches every checkpoint on disk: True
```

That verification is a measurement in this file rather than a test, because the test that would
perform it is exactly the one CI cannot run. Naming it here is the honest form: the numbers are
data the suite asserts against, and the date and machine they were read on are recorded with them.

**Gate after the redesign: 1622 passed, 0 skipped, floor 1622** — a number the runner can reach.

## D-190's own text was stale for one commit, and a wider sweep found nothing else

The paragraph above ("Pinned so it cannot drift again") was written for the version CI rejected. It
said **two** tests reading the constants **off the checkpoints**; `main` has **three** asserting
against `DECLARED_VIDEO_PREPROCESSORS`. Appending the CI-failure section left the entry
contradicting itself — the repo's own rule is that corrections go *in* the cell, not in prose after
it — so both D-190 and the M5.2 cell are corrected in place rather than extended again.

**A wider sweep for the same class of rot found none.** Every `test_*` name cited in PROGRESS.md,
DECISIONS.md, README.md, BLOCKED.md and AUDIT_REPORT.md was resolved against the 1,505 test
functions actually defined:

```
distinct names cited in docs   : 133
  of those, test FILE names    :  47   (tests/test_asr.py, not a function)
  cited functions NOT DEFINED  :   5   -> all five checked individually
```

All five were false positives of the probe, not of the ledger:

* `test_a_changed_source_is_extracted_again` and `test_a_crashed_run_leaves_no_record` — the docs
  cite a **prefix** of a longer real name (`…_rather_than_served_from_the_old_output`,
  `…_an_earlier_settings_run_could_match`).
* `test_counting_tokens_cannot_send_confidential_text_before_the_zdr_gate` — exists; the probe's
  own line-healing had glued `UNHELD` onto it from the next line.
* `test_the_cli_refuses_flags_whose_prerequisites_are_absent` — **deliberately removed by D-149**,
  which explains at length that it "looked like coverage" while asserting only `main(...) == 2`,
  and `tests/test_pipeline.py:494` carries a tombstone comment saying where it stood. The citation
  is history, correctly recorded.

The first count was **52**, which was the probe matching test *file* names and truncated prefixes.
Reporting 52, or even 5, would have been reporting the probe rather than the repository — the same
failure as this session's two `pgrep` matches and the gate-attack harness. Verified down to zero.
