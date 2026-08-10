# --help named a command that was not installed

> Measured 2026-08-10 on hawapc01 against `5bb7f18`, from a wheel built by
> `scripts/build-wheel.sh` and installed into a fresh CPython 3.12.13.

D-141 saw two of these in passing and recorded them unfixed. Measured across all five, in both
invocation modes, the fault is universal.

## Before

```
console scripts (from the wheel)
  hawedit                  usage: hawedit.pipeline [-h] [--work-dir WORK_DIR] …
  hawedit-asr-bench        usage: hawedit-asr-bench [-h] --audio-root AUDIO_ROOT …
  hawedit-asr-setup        usage: hawedit-asr-setup [-h] [--distribution DISTRIBUTION]
  hawedit-credentials      usage: hawedit.credentials [-h] [--check]
  hawedit-editorial-bench  usage: hawedit-editorial-bench [-h] [--media-root MEDIA_ROOT]

python -m (from source)
  hawedit.pipeline         usage: hawedit.pipeline [-h] [--work-dir WORK_DIR] …
  hawedit.bench            usage: bench.py [-h] --audio-root AUDIO_ROOT --host HOST …
  hawedit.wsl_setup        usage: wsl_setup.py [-h] [--distribution DISTRIBUTION]
  hawedit.credentials      usage: hawedit.credentials [-h] [--check]
  hawedit.editorial_bench  usage: editorial_bench.py [-h] [--media-root MEDIA_ROOT] …
```

`hawedit --help` names `hawedit.pipeline`, which is not a command. `python -m hawedit.bench --help`
names `bench.py`, which is not a command either. Two modules set a fixed module `prog`; three set
none and got argparse's `basename(sys.argv[0])`. **Every one of the five is wrong in one of its two
modes**, and argparse reuses `prog` in error messages, where a wrong command name costs most.

## After

```
python -m (from source)
  hawedit.pipeline         usage: python -m hawedit.pipeline [-h] [--work-dir WORK_DIR]
  hawedit.bench            usage: python -m hawedit.bench [-h] --audio-root AUDIO_ROOT --host HOST
  hawedit.wsl_setup        usage: python -m hawedit.wsl_setup [-h] [--distribution DISTRIBUTION]
  hawedit.credentials      usage: python -m hawedit.credentials [-h] [--check]
  hawedit.editorial_bench  usage: python -m hawedit.editorial_bench [-h] [--media-root MEDIA_ROOT]
  hawedit.smoke            usage: python -m hawedit.smoke [-h] [--yes] [--video VIDEO]

console scripts (from a freshly built and installed wheel)
  hawedit                  usage: hawedit [-h] [--work-dir WORK_DIR] [--media-id MEDIA_ID]
  hawedit-asr-bench        usage: hawedit-asr-bench [-h] --audio-root AUDIO_ROOT --host HOST
  hawedit-asr-setup        usage: hawedit-asr-setup [-h] [--distribution DISTRIBUTION]
  hawedit-credentials      usage: hawedit-credentials [-h] [--check]
  hawedit-editorial-bench  usage: hawedit-editorial-bench [-h] [--media-root MEDIA_ROOT]
```

Ten of ten name a command that exists.

### The first push was refused by CI, and the fault was in my test

```
E  AssertionError: hawedit --help says 'C:\\somewhere\\venv\\Scripts\\hawedit'
E  assert 'C:\\somewher...ipts\\hawedit' == 'hawedit'
```

The fake `argv[0]` was a `C:\…\Scripts\x.exe` string literal. On POSIX `\` is not a path
separator, so `Path.stem` returned the whole string and all five parametrised cases failed on the
Linux runner while passing here. **The rule was right on both platforms** — `/usr/bin/hawedit` and
`…\Scripts\hawedit.exe` both yield `hawedit` — and only the fixture was Windows-only. Rebuilt
with `Path(...)` so separators are native, and parametrised over the bare and `.exe` shapes, which is
strictly more than the original checked. That is the second platform-bound test of mine after
D-137's `pytest.skip`, so this one exercises both cases rather than assuming one.

## Proof

```
baseline green: True

RED  pipeline goes back to a fixed module prog (the defect, console-script side)
RED  credentials goes back to a fixed module prog
RED  bench drops prog entirely (the defect, python -m side: a bare bench.py)
RED  wsl_setup drops prog entirely
RED  editorial_bench drops prog entirely
RED  the rule inverts: a module file is treated as a console script
RED  the -m branch drops the runnable `python -m` prefix
RED  the console-script branch keeps the .exe Windows appends
RED  an empty argv[0] yields an empty program name

9/9
restored and green: True
```

The tests drive both modes through the real `main()` of every module in `[project.scripts]` and read
the line argparse prints — not the `prog=` argument echoed back. **The control is that the two modes
must print different names:** a hard-coded `prog` satisfies one of the two assertions, so asserting
only one of them would be satisfied by exactly the defect this fixes.

Gate: `VERIFY OK — hawedit gate green`, 1412 tests.
