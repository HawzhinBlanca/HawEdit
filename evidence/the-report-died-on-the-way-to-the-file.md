# The report died on the way to the file

> Measured 2026-08-09 on hawapc01 — Windows 11, cp1252 — against `db2cb57`.

Found by running the real 38-minute file, not by reading code. The pipeline finished: Stage 0
demuxed 38 minutes, the canonical LLM-7B + CTC-3B pass transcribed 547 regions on two 3090 Ti, and
`transcript.raw.json` was written. Then the CLI printed its report and died.

```
python -m hawedit.pipeline "ZAR38MinTest.mp4" --omni-asr --work-dir ... --json > report.json

  File "src/hawedit/pipeline.py", line 1556, in main
    print(json.dumps(run.to_dict(), ensure_ascii=False, indent=2))
  File ".../encodings/cp1252.py", line 19, in encode
    return codecs.charmap_encode(input, self.errors, encoding_table)[0]
UnicodeEncodeError: 'charmap' codec can't encode characters in position 45257-45260

exit 1 · report.json: 0 bytes
```

## Why, measured rather than assumed

```
locale.getpreferredencoding(False)  cp1252
redirected stdout                   encoding cp1252   errors surrogateescape
redirected stderr                   encoding cp1252   errors backslashreplace
```

Python takes the streams' encoding from the locale. On a console it does not matter — Python writes
UTF-16 to the Windows terminal. Redirect, and the codec is the ANSI code page, while the product's
output is Sorani.

## Three behaviours, one cause

**1 · Outside cp1252 → raises.** All Kurdish, and `✓ ✗ →`. Reproduced without ASR by feeding the
already-written transcript back in, so the run costs a Stage 0 rather than ten GPU minutes:

```
--transcript ZAR38MinTest.transcript.raw.json --json > out.json
  exit 1 · 0 bytes · same UnicodeEncodeError at position 45263
```

**2 · Inside cp1252 → the wrong byte, silently.** A run with no transcript exits normally and
writes a file that is not UTF-8:

```
stdout of a blocked run: 1,692 bytes, 9 of them high
  0xB7 ×5  U+00B7 MIDDLE DOT
  0xA7 ×1  U+00A7 SECTION SIGN
  0x96 ×1  U+2013 EN DASH
  0x97 ×2  U+2014 EM DASH
valid UTF-8: False — 'utf-8' codec can't decode byte 0xb7 in position 46
```

**3 · stderr mangles instead of raising**, because its default handler is `backslashreplace`:

```
✗ canonical OmniASR WSL2 runtime is not provisioned
reaches the log as:  \u2717 canonical OmniASR WSL2 runtime is not provisioned
```

That is how it appeared in this loop's own captured stderr, unnoticed, for days.

## The fix

`src/hawedit/cli.py` — `use_utf8_streams()`, the first statement of all five `main()`s. Only the
encoding is set; the error handlers stay as the interpreter left them, because UTF-8 encodes
everything this product produces and they stop being reachable for text.

## Proof: the same command, and the artifact

```
--transcript ZAR38MinTest.transcript.raw.json --json > report.json

report.json          1,010,979 bytes
decodes as UTF-8     True
keys                 20
transcript chars     35,185
words                6,104
first characters     کاکە بیلال …
speech_without_transcription_ms  664   (2 gaps, D-110's field intact)
stderr               0 bytes
exit 1               — Stage 4 is BLOCKED.md #3, which is the correct reason
```

## The wiring, which is the part that would have rotted

`tests/test_cli.py` reads `[project.scripts]` from `pyproject.toml` and drives every declared entry
point under `PYTHONIOENCODING=cp1252`, asserting the Sorani sentinel's UTF-8 bytes on stdout *and*
stderr. It does not check that `use_utf8_streams` is called — a call placed after the first write
would pass that, and an entry point added later would not be covered at all.

Forcing the codec is also what makes it mean anything on CI: the runner is Linux with a UTF-8
locale, where every one of these passes with no fix whatsoever.

```
baseline fails: False

RED  pipeline.py does not call it
RED  bench.py does not call it
RED  wsl_setup.py does not call it
RED  credentials.py does not call it
RED  editorial_bench.py does not call it
RED  the helper is a no-op
RED  only stdout is pinned
RED  it pins the locale's codec instead of utf-8

8/8
```

Five of the eight are the wiring, deliberately: D-105, D-108 and D-112 were all *the function is
tested, the trip to it is not*, and a helper five callers have to remember is that shape exactly.

Gate: `VERIFY OK — 1248 passed, 0 skipped`.
