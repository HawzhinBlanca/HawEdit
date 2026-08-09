# Adversarial pass #17 — the throughput harness

> Run 2026-08-09 on hawapc01 against `e509c64`.
> Target: **M0.7**, DONE — never attacked, and every claim in it is a number.

The hard rule: *"Unmeasured is None, never 0.0 — and never a score. A number carries the hardware and
adapter that produced it."* So each mutation turns a `None` into a plausible zero, or a refusal into
an average.

```
CAUGHT  a corpus with no long audio reports a 0.0 failure rate
CAUGHT  the long-audio rate no longer refuses mixed hardware
CAUGHT  measurements from two machines are combined
CAUGHT  RTF is inverted — duration over wall clock
CAUGHT  a failed item reads as a successful one
CAUGHT  an unprobed VRAM figure becomes 0 instead of None      per measurement
MISSED  an unmeasured peak VRAM aggregates to 0                per model report
MISSED  an empty score set reports mean RTF 0.0
CAUGHT  the adapter is named by class alone (D-097)

7/9
```

The rule is held where each measurement is taken and unheld where they are summarised — which is the
layer that gets written and read.

## What the unheld report would have published

```
ModelReport(scores=(), peak_vram_bytes=None).to_dict()
  mean_rtf                   None      would have been 0.0
  worst_rtf                  None      would have been 0.0
  peak_vram_bytes            None      would have been 0
  long_audio_failure_rate    None
```

`mean_rtf: 0.0` is not a blank — it is *infinitely fast*, in the field §3 Stage 1 exists to warn
about. `worst_rtf: 0.0` says it was never slower than that. `peak_vram_bytes: 0` says a 17 GiB model
used no memory, and §6 sizes two GPUs off that number.

## The tests, and the control

Both assert on `to_dict()` — the JSON a capacity plan is read off — not on the properties. And the
control is the half that matters: returning `None` unconditionally satisfies both and throws away
every real figure, so a probed run must still report 17 GiB and a scored run its mean and worst.

## My first VRAM test was one call away from the defect

The mutation is inside `run_benchmark`:

```python
peak_vram_bytes=max(vram) if vram else 0
```

My test constructed a `ModelReport` directly, so it only exercised `to_dict`'s passthrough and
**passed with the mutation in place** — the audit reported it as still surviving, which is the only
reason I noticed. It drives `run_benchmark` now, whose session supplies no probe, with a
probe-supplying control beside it.

That is the same shape this pass series keeps finding in the suite. Finding it in my own test on the
re-run is the argument for re-running the audit rather than assuming the fix landed.

```
after: 9/9
```

No production code changed.

Gate: `VERIFY OK — 1311 passed, 0 skipped`.
