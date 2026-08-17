# Three refusals in the renderer that nothing would miss

A guard-revert sweep over the two modules that build the deliverable — `delivery.py`, which writes
the SRT/EDL/ASS/JSON a client opens, and `render.py`, which encodes the MP4 itself. D-149's method:
every `raise` located by parsing rather than by grep, replaced one at a time with `pass` at the
same indent, `ruff format`ed, the **whole** suite run each time against a baseline verified green
first, and the file restored byte-identical after each.

```
baseline: GREEN (1630 passed)

--- delivery.py: 12 refusals ---   all HELD
--- render.py:   11 refusals ---   3 UNHELD

held 20/23, unheld 3
  render.py:224  {source_width}x{source_height} cannot be cropped to {aspect}
  render.py:299  raise ValueError(rate)            (a frame rate of 0/0)
  render.py:443  encode failed ({returncode}): {ffmpeg's stderr}
restored byte-identical: True     suite after restore: GREEN
```

`delivery.py` came back **12/12**, each held by a test named for the property — negative
timestamps, unreadable cue timings, an empty SRT, an incomplete sentence, a sentence outside the
clip, non-integer and non-positive frame rates, a negative in-point, a zero-length clip, a clip
shorter than one frame. Nothing to do there, and worth saying so: the sweep's value is as much in
the modules it clears as in the ones it does not.

**No production code changed.** All three refusals were already there and already correct. What was
missing was anything that would notice their removal.

## The one that matters: a failed encode

```python
if result.returncode != 0 or not output.exists():
    raise RenderError(f"encode failed ({result.returncode}): {…stderr…}")
```

This is the last check between ffmpeg and a client. Deleting it left the whole suite green, and the
fall-through is not harmless — the next line is `probe_duration_ms(output, binary)`, so a failed
encode becomes whatever a duration probe says about a file that may not be there.

Reproduced with a **real** ffmpeg failure rather than a mock: the output path is a directory, which
is what a stale run directory looks like. `output.parent.mkdir(parents=True, exist_ok=True)` runs
first and succeeds, so this reaches the encoder exactly as a real fault would.

```
RenderError: encode failed (4294967283): [out#0/mp4 @ …] Error opening output …\clip.mp4:
Permission denied
Error opening output file …\clip.mp4.
Error opening output files: Permission denied
```

The test asserts ffmpeg's own words are in the message, not just that something was raised. A
generic "encode failed" would satisfy the match and tell an operator nothing, and ffmpeg is the only
thing that knows why it stopped.

## The other two

**`render.py:224` — a source too small to crop.** Measured: `1x1000`, `1000x1` and `2x2` all reduce
to a zero dimension once the even-number rounding `yuv420p` needs is applied. Without the refusal
that is an ffmpeg error at encode time or a frame of nothing.

**`render.py:299` — a frame rate of `0/0`.** That is what ffprobe reports for a stream whose rate it
cannot determine. Without the refusal the ratio is evaluated and the caller gets `ZeroDivisionError`
from inside a rate probe — and since `frame_duration_ms` divides by the result, the traceback would
point one function further away still. ffprobe's answer is supplied rather than hunted for, the way
the symlink tests supply the kernel's: what is scarce is a file that provokes it, not the refusal
under test.

## The control earned its place immediately

`test_a_source_too_small_to_crop_is_refused` asserts that the fixture's own `640x360` still produces
a filter. The first version of that line passed the target size positionally — and `crop_filter`'s
third and fourth parameters are `focus_x` and `focus_points`, not `target_width`/`target_height`:

```
TypeError: 'int' object is not iterable    src\hawedit\render.py:227
```

Every refusal in the loop above still fired, because all three degenerate sources raise *before*
reaching the focus-point branch. A test with only the `pytest.raises` half would have passed while
calling the function wrongly, and the scratch probe that measured these cases had the same bug and
reported clean output.

## Mutation audit — 3/3, lint-clean

```
baseline: GREEN (1633 passed, 86 warnings in 150.76s)

CAUGHT   a failed encode is no longer refused
         by 1: test_a_failed_encode_is_refused_with_ffmpegs_own_words
CAUGHT   a source too small to crop is no longer refused
         by 1: test_a_source_too_small_to_crop_is_refused
CAUGHT   a zero frame rate is divided by instead of refused
         by 1: test_a_frame_rate_of_zero_is_refused_rather_than_divided_by

file restored byte-identical: True
3/3 caught
suite after restore: GREEN
```

**The first run of this audit was not clean, and the harness now says so out loud.** Deleting the
whole `if` block around the encode refusal leaves `result` unused; ruff reports it; and
`tests/test_gate.py` runs the real `verify.sh`, so `test_nested_fast_run_is_still_allowed` and its
neighbours failed alongside the genuine defender. The mutation now replaces only the `raise` — the
sweep's own form — and each guard is caught by exactly the one test written for it. The audit
harness prints `[LINT DIRTY — the gate tests fail for free]` rather than a quiet marker, because
this is the third time in this session that a lint-dirty mutation dressed itself up as a held guard.
