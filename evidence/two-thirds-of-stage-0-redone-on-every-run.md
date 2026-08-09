# Two thirds of Stage 0, redone on every run

> Measured 2026-08-10 on hawapc01 against `b1da684`, source
> `C:\Users\Wareen\Desktop\Test Videos\ZAR38MinTest.mp4` (82,446,418 bytes, 2313.7 s).

BLUEPRINT §1 calls the stages **re-runnable**. Stage 0 re-derived everything, every time.

## Before

```
Stage 0, first run:
  extract_audio             69.9 s
  extract_proxy             30.3 s
  detect_speech             18.2 s
  probe_duration_ms          0.1 s
  detect_shots              32.9 s
  TOTAL                    151.4 s

speech regions: 547   shot cuts: 138
audio.wav: 74,039,412 bytes   proxy.mp4: 51,124,346 bytes

second run into the SAME work directory:
  extract_audio (again)     69.5 s     audio.wav rewritten: True
  extract_proxy (again)     30.3 s     proxy.mp4 rewritten: True
```

**100.2 s of 151.4 s — 66% — redone.** Not "computed and discarded" and not "never computed": a
third thing, *computed again from scratch* with the previous answer sitting beside it.

## The key, chosen by measurement

SHA-256 of the whole 82 MB source: **0.1 s**. Against 100.2 s, the cheap key bought nothing, so
size-and-mtime was rejected — it needs a tolerance guessed for two runs landing in the same second,
and it cannot see a same-length replacement.

## After

```
Stage 0 on ZAR38MinTest.mp4, first run:
  extract_audio             74.5 s
  extract_proxy             31.1 s
  detect_speech             18.7 s
  probe_duration_ms          0.1 s
  detect_shots              33.6 s
  TOTAL                    157.9 s

speech regions: 547   shot cuts: 138
audio.wav: 74,039,412 bytes   proxy.mp4: 51,124,346 bytes

second run into the SAME work directory:
  extract_audio (again)      0.1 s
  extract_proxy (again)      0.1 s
  audio.wav rewritten: False
  proxy.mp4 rewritten: False
```

**105.6 s → 0.2 s.** (First-run totals move 151.4 → 157.9 s across the two measurements; that is
run-to-run variance on this machine, and the two digests inside it cost 0.2 s.)

The artifacts, after being reused rather than written:

```
audio.wav: recorded 74,039,412 == on disk 74,039,412 -> True
  source_sha256 bd004519e4ed0254…  command has 18 parts, dest excluded: True
proxy.mp4: recorded 51,124,346 == on disk 51,124,346 -> True
  source_sha256 bd004519e4ed0254…  command has 16 parts, dest excluded: True
digest matches the real source: True
reused audio still: 16000 Hz 1 ch 16 bit 2313.7 s
```

## Proof

```
baseline green: True   (33/33 tests/test_ingest.py)

RED  the extraction is unconditional again (the defect: 100.2 s redone)
RED  reuse keyed on the destination existing, not on the source's digest
RED  the recorded command is not compared, so old settings' output is kept
RED  the recorded output size is not compared, so a truncated file is reused
RED  an unreadable or absent provenance record counts as a match
RED  the stale record is left in place while the new run happens
RED  an extraction that wrote nothing is reported as success
RED  the audio format is only checked on the run that wrote the file

8/8
restored and green: True
```

Every one names the test that caught it. The controls are the ones that pull the other way: reuse
must *not* happen when the content changed, when the settings changed, when the file was truncated,
when the record is unreadable, or when a crashed run left a size collision behind — a mechanism that
simply never reused would satisfy the first assertion and fail all five.

## The first pass was 7/8

The digest comparison SURVIVED being replaced by `True`. `test_a_changed_source_…` extracted from
`FIXTURE`, then from `other.mp4` — and `-i <source>` is *part of the recorded command*, so the
command comparison caught it and the digest was never consulted. The test named the digest's rule and
measured the command's.

Rewritten to hold the source path constant and overwrite its content with a different recording,
which is the only way to bind the digest — and the case that actually happens: a re-export, a fixed
audio track, a file swapped in place under a work directory nobody cleaned.

That is the eighth consecutive pass whose real finding was an assertion that could not distinguish
the rule it named (D-124, D-125, D-126, D-128, D-129, D-130, D-131).

## Found on the way

The existing command-capturing tests went red: their fake `_run` recorded argv without writing a
file, so the sidecar's own `stat()` raised a bare `FileNotFoundError`. ffmpeg exiting 0 and writing
nothing is real — it is the shape `curl --fail` exists for (D-121) — and it surfaced as a complaint
about provenance bookkeeping rather than about the pass that produced nothing. Now an `IngestError`
naming the destination, with the fake writing its output the way ffmpeg does.

Gate: `VERIFY OK — hawedit gate green`, 1326 tests.
