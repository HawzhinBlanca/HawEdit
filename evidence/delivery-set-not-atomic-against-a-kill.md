# §2's delivery set was not atomic against a kill

> Measured 2026-08-10 on hawapc01 against `b24ce15`, real runs of `run_pipeline` over
> `tests/fixtures/kurdish-speech-3cuts.mp4` with ffmpeg 8.1.1-full.

`§10/10` asks for atomic, resumable delivery. D-072 got the sidecar set to all-or-none against a
*failing write* — it builds all three before writing any, and its `except` unlinks them. The clause
is `except (DeliveryError, RenderError, OSError)`. A Ctrl-C raises `KeyboardInterrupt`, which is a
`BaseException` and not in that set; a `SIGKILL` runs no clause at all.

## Reproduced

A clean run first, for the reference set:

```
--- run 1: clean ---
delivery stage: Delivery
   atomicity-s0-0.ass
   atomicity-s0-0.edl
   atomicity-s0-0.json
   atomicity-s0-0.mp4
   atomicity-s0-0.srt
```

The same run, interrupted at the instant the second of the three sidecar writes begins:

```
--- run 2: interrupted the instant the SRT write begins ---
  KeyboardInterrupt propagated: the operator pressed Ctrl-C here
on disk afterwards:
   atomicity-s0-0.ass
   atomicity-s0-0.json
   atomicity-s0-0.mp4
missing from the interrupted set: ['atomicity-s0-0.edl', 'atomicity-s0-0.srt']
```

A playable captioned MP4 and §2's editing manifest, with no SRT and no EDL beside them — and no
report at all, because the process died. Then the part that turns a partial set into a dead end:

```
before the retry: ['atomicity-s0-0.ass', 'atomicity-s0-0.json', 'atomicity-s0-0.mp4']
retry RAISED FileExistsError: refusing to overwrite existing delivery artifact(s): ...ass, ...
after the retry: ['atomicity-s0-0.ass', 'atomicity-s0-0.json', 'atomicity-s0-0.mp4']
```

D-071's guard refuses when *any* of the five paths exists. The files the interrupted run stranded
are what makes the retry impossible, so one keystroke ended that work directory's usefulness.

## After the fix

Same interruption, same work directory:

```
--- run 2: interrupted the instant the SRT write begins ---
  KeyboardInterrupt propagated: the operator pressed Ctrl-C here
missing from the interrupted set: ['atomicity-s0-0.delivery.provenance.json',
                                   'atomicity-s0-0.edl', 'atomicity-s0-0.srt']

===== RETRY =====
before the retry: ['atomicity-s0-0.ass', 'atomicity-s0-0.json', 'atomicity-s0-0.mp4']
retry finished. delivery: Delivery
after the retry: ['atomicity-s0-0.ass', 'atomicity-s0-0.delivery.provenance.json',
                  'atomicity-s0-0.edl', 'atomicity-s0-0.json', 'atomicity-s0-0.mp4',
                  'atomicity-s0-0.srt']
```

and the recovery is in the emitted report rather than silent:

```
clean run    resumed_over in emitted JSON: []
recovery run resumed_over in emitted JSON: ['atomicity-s0-0.ass', 'atomicity-s0-0.mp4',
                                            'atomicity-s0-0.json']
```

The control matters as much as the case: a *finished* delivery is still refused, which the two
D-071 tests now assert against a five-file set plus its record.

## What changed

* `_write_atomic` — staged `.<name>.tmp`, one rename, dotfile unlinked if the write fails. Used for
  the ASS and all three sidecars. A kill can no longer leave a file that exists and is half-written.
* `{clip_id}.delivery.provenance.json` — written **last**, recording each artifact's byte length.
  `_assert_no_existing_artifacts` refuses only a set whose record exists and matches; no record,
  unreadable record, missing file or wrong length all mean "redo".
* `PipelineRun.resumed_over` — the abandoned artifact names, in the report and in the JSON.

## Proof

```
baseline green: True

RED  the defect restored: any leftover file refuses, so an interrupted run wedges the dir
RED  the record is no longer required, so an abandoned attempt reads as a delivery
RED  the guard stops refusing altogether, so a finished delivery is overwritten
RED  the record is written first, so a kill during the sidecars leaves a complete-looking set
RED  the record stops recording sizes, so a torn artifact still reads as complete
RED  a missing artifact no longer falsifies the record
RED  the staged write goes straight to the target again, so a kill leaves half a file
RED  a failed staged write leaves its dotfile behind
RED  the report stops naming what it overwrote
RED  the report hard-codes a recovery it did not perform

10/10
restored and green: True
```

The first pass was **9/10**. The survivor let a missing artifact `continue` past the record check
instead of falsifying it, which left every other test green and would have turned "someone deleted
the SRT" into a permanent refusal to produce one.

## Five existing tests changed, and all five got stronger

`_existing_artifact` planted one file, because the guard refused on one file. It now plants a
finished delivery — five artifacts plus the record, written by the production writer so the plant
cannot drift from a real run. The three tests that watch `Path.write_text` resolve a staging name
back to its target through `_write_target`, so they still assert on which artifact is written rather
than on the staging convention. `_sidecars_on_disk` excludes the record, which is a `.json` beside
the sidecars and not one of them.

Gate: `VERIFY OK — hawedit gate green`, 1434 tests (floor 1427 → 1434).
