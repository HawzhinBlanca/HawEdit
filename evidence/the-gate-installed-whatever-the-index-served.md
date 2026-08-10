# The gate installed whatever the index served

> Measured 2026-08-10 on hawapc01 against `149624d`.

§10/10: *"pinned and checksummed supply chain"*. D-120 made the wheel build reproducible; D-121
pinned the ffmpeg archive to a commit and verified its SHA-256 before unzipping. The Python packages
the gate executes were resolved fresh on every run.

## Before

```
declared in pyproject (all extras): 17
installed in this venv:             70
installed but NOT declared anywhere (transitive): 54
```

Direct dependencies were exactly pinned — 13 of 17 with `==`, four with ranges — and **54 more
arrived with no version and no checksum**:

```
  annotated-doc      0.0.5      huggingface-hub    0.36.2
  anyio              4.14.2     humanfriendly      10.0
  certifi            2026.7.22  idna               3.18
  charset-normalizer 3.4.9      iniconfig          2.3.0
  chunspell          2.0.4      jinja2             3.1.6
  …                             …
```

24% pinned by version, **0% by checksum**.

## After

```
distributions pinned:  33
sha256 hashes present: 350
pins with no hash:     0 []
```

`requirements/gate-linux-py311.txt`, the full `.[dev,media]` closure for the gate's own platform.
CI installs it with `--require-hashes`, so every artifact is verified before it is unpacked, then
adds the project itself with `--no-deps`.

The lock regenerates from a committed script:

```
$ bash scripts/lock-gate-deps.sh
wrote /c/Users/Wareen/Desktop/HawEdit/requirements/gate-linux-py311.txt
  33 distributions pinned, 350 sha256 hashes
```

Run twice, byte-identical output — the target is fixed in the script (`--python-platform linux
--python-version 3.11`) rather than inherited from whoever runs it.

## Proof

```
baseline green: True

RED  CI installs the extras fresh again (the defect: 54 unpinned transitives)
RED  CI installs from the lock but stops verifying the checksums
RED  the project is installed WITH its dependencies, resolving them unpinned alongside
RED  one distribution loses its hashes in the lock
RED  the lock is truncated to the direct dependencies only
RED  a dependency is declared for the gate but missing from the lock
RED  the lock script stops generating hashes
RED  the lock script targets this Windows host instead of the runner
RED  the project itself is pinned in the lock, which cannot be hashed

9/9
restored and green: True
```

**The first pass was 8/9.** The survivor was "one distribution loses its hashes": deleting the
trailing backslash from `iniconfig==2.3.0 \` leaves the orphaned `--hash` lines sitting under it, so
a check that looks for `--hash` *between two pins* still finds them. pip reads a requirement as
ending where the continuation stops, so that pin owns no hashes at all and `--require-hashes`
rejects the entire install. The check is structural now: a pin line must end with a continuation.

## The prose-grep trap again

The control was first written as `assert "-e '.[dev,media]'" not in workflow`, and the workflow
comment *quotes* that command to record what it replaced:

```
E  AssertionError: CI still resolves the extras fresh, so the hashed lock is not what it installs
E  "-e '.[dev,media]'" is contained here:
E    npacked. `-e '.[dev,media]'` resolved fresh on every
```

D-121 hit this in `fetch-ffmpeg.sh`, where the script *explains* `--fail` in a comment. This project
quotes the wrong command while correcting it, so a test over prose matches the correction. It reads
command lines only now.

## What this does not cover, stated plainly

* The **developer venv** on this Windows host still resolves freely. The lock targets the gate of
  record; a Windows lock would pin different wheels and is not what CI verifies.
* The **`gpu`, `asr` and `cloud`** extras are unlocked. CI does not install them, `asr` is excluded
  on Windows by its own marker, and a lock nothing exercises is a claim rather than a guarantee.

Gate: `VERIFY OK — hawedit gate green`, 1384 tests.
