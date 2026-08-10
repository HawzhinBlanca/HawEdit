# Four of five entry points

> Measured 2026-08-10 on hawapc01 against `b0f0391`.

The loop's step 1(b) names `AUDIT_REPORT.md` as a place claims drift. Its "Verification evidence"
section had never been checked.

## The claim

> Clean Python 3.12 wheel install: `pip check` clean; `hawedit`, `hawedit-asr-bench`,
> `hawedit-editorial-bench` and `hawedit-asr-setup` all start from the installed wheel.

Four. And:

```
[project.scripts] declares 5 entry points:
  hawedit                    -> hawedit.pipeline:main
  hawedit-asr-bench          -> hawedit.bench:main
  hawedit-asr-setup          -> hawedit.wsl_setup:main
  hawedit-credentials        -> hawedit.credentials:main
  hawedit-editorial-bench    -> hawedit.editorial_bench:main

declared but NOT named in AUDIT_REPORT: ['hawedit-credentials']
```

The missing one is the credential panel — the entry point that handles the API key. It arrived with
M2.8 and the sentence was never re-derived: D-127's *five repositories* and D-129's *four blocked
stages*, a third time.

## The claims are true; the list was short

A wheel built from this tree, installed into a fresh CPython 3.12.13:

```
starting each one from the installed wheel (--help, so nothing is billed or written):
  OK   hawedit                    exit 0  usage: hawedit.pipeline [-h] [--work-dir WORK_DIR] …
  OK   hawedit-asr-bench          exit 0  usage: hawedit-asr-bench [-h] --audio-root AUDIO_ROOT …
  OK   hawedit-asr-setup          exit 0  usage: hawedit-asr-setup [-h] [--distribution …
  OK   hawedit-credentials        exit 0  usage: hawedit.credentials [-h] [--check]
  OK   hawedit-editorial-bench    exit 0  usage: hawedit-editorial-bench [-h] [--media-root …

Checked 4 packages — All installed packages are compatible

wheel: hawedit-0.1.0-py3-none-any.whl, 346,694 bytes, 55 entries
  OK   the Kurdish font             ['hawedit-0.1.0.data/data/share/hawedit/assets/fonts/NotoNaskhArabic-Regular.ttf']
  OK   its OFL licence              ['hawedit-0.1.0.data/data/share/hawedit/assets/fonts/OFL.txt']
  OK   the model-source manifest    ['…/models/revisions.json', '…/models/sources.json']
  OK   the WSL worker               ['hawedit/asr_worker.py']
  OK   the setup module             ['hawedit/wsl_setup.py']
```

## Proof

```
baseline green: True

RED  the report drops hawedit-credentials again (the defect)
RED  the report names a console script that does not exist
RED  the report keeps the list right and lets the count go stale
RED  a sixth console script is declared and the report is not updated
RED  the wheel-contents claim stops naming the Kurdish font
RED  the wheel-contents claim names a file that is not in the tree

6/6
restored and green: True
```

**The first pass was 4/6, and one of the survivors was the primary defect itself.**

## The prose-grep trap, three for three

Dropping `hawedit-credentials` from the list left the suite green: the correction note in the same
bullet *names* the entry point it records as once-omitted, so a check over the whole section read it
from the explanation rather than from the claim.

That is the third occurrence in this repo:

* D-121 — `fetch-ffmpeg.sh` **explains** `--fail` in a comment, and the test asserting `--fail`
  was present matched the comment;
* D-139 — the gate workflow **quotes** `-e '.[dev,media]'` to say what it replaced, and the control
  asserting its absence matched the quote;
* here — the correction **names** the omitted script.

This project's convention is to quote the wrong thing while correcting it. Every check over
documentation therefore has to read the claim and not its history. The test now takes the bullet up
to `**Corrected`.

## And one mutation of mine measured nothing

*"the wheel-contents claim names a file that is not in the tree"* replaced the first
`` `models/revisions.json` `` in the file. There are two — the other is in "Secondary debt"
(D-073) — so it changed the one the test does not read and reported SURVIVED. Re-anchored on text
unique to the section; caught. Same class as D-137's retry mutation.

## Found in passing, measured, not fixed here

```
  hawedit               -> usage: hawedit.pipeline [-h] …
  hawedit-credentials   -> usage: hawedit.credentials [-h] [--check]
```

Both set `prog=` to the module path, so the wheel's own `--help` names a command that does not
exist as a command. `hawedit-asr-bench`, `hawedit-asr-setup` and `hawedit-editorial-bench` print
their real names. `smoke.py` sets a module prog too and is *not* a console script, so there it is
correct. The fix is to derive the name from how the process was invoked — `__main__.py` in `argv[0]`
means `python -m` — which belongs in `cli.py` beside `use_utf8_streams()` and needs its own decision
about the rule, so it is recorded rather than half-done.

Gate: `VERIFY OK — hawedit gate green`, 1396 tests.
